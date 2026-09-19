"""How a repository has been touched: commits, authors, fixes, threads, noise.

Reads stay inside a small window so a large repo does not become hundreds of
API calls. Nothing here closes, hides, or deletes a GitHub object.
"""
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import github_tools
import jev_gate

MAX_COMMITS = 80
FIX_RE = re.compile(r"(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.I)


def _repo() -> str:
    return github_tools._repo()


def _slim_commit(commit: dict, files: list[str] | None = None) -> dict:
    body = commit.get("commit") or {}
    author = (body.get("author") or {}).get("name") or ((commit.get("author") or {}).get("login")) or "unknown"
    message = (body.get("message") or "").split("\n", 1)[0][:180]
    return {
        "sha": commit.get("sha") or "",
        "short": (commit.get("sha") or "")[:7],
        "message": message,
        "author": author,
        "date": (body.get("author") or {}).get("date"),
        "files": files or [],
    }


def load_window(count: int = 30) -> dict:
    count = max(1, min(int(count or 30), MAX_COMMITS))
    repo = _repo()
    raw = github_tools._request("GET", f"/repos/{repo}/commits", params={"per_page": count})
    if not isinstance(raw, list):
        raw = []
    slim = [_slim_commit(commit) for commit in raw[:count]]

    def files_for(sha: str) -> list[str]:
        if not sha:
            return []
        detail = github_tools._request("GET", f"/repos/{repo}/commits/{sha}")
        return [item.get("filename") for item in (detail.get("files") or []) if item.get("filename")][:40]

    head = slim[:20]
    with ThreadPoolExecutor(max_workers=6) as pool:
        listed = list(pool.map(files_for, [item["sha"] for item in head]))
    for item, names in zip(head, listed):
        item["files"] = names
    issues = (github_tools.list_open_issues(20).get("issues") or [])
    pulls = (github_tools.list_pull_requests(15).get("pulls") or [])
    authors = {item["author"] for item in slim if item["author"]}
    return {
        "commits": slim,
        "issues": issues,
        "pulls": pulls,
        "contributors": len(authors),
        "say": f"{len(slim)} commits in view, {len(authors)} authors, {len(issues)} open issues, {len(pulls)} open pull requests.",
    }


def who_touched(path: str) -> dict:
    repo = _repo()
    path = (path or "").strip()
    if not path:
        raise RuntimeError("Name a file path.")
    raw = github_tools._request("GET", f"/repos/{repo}/commits", params={"path": path, "per_page": 20})
    if not isinstance(raw, list):
        raw = []
    authors: dict[str, dict] = defaultdict(lambda: {"count": 0, "last": None})
    commits = []
    for commit in raw:
        row = _slim_commit(commit)
        authors[row["author"]]["count"] += 1
        if not authors[row["author"]]["last"]:
            authors[row["author"]]["last"] = row["date"]
        commits.append(row)
    people = [{"name": name, **meta} for name, meta in authors.items()]
    people.sort(key=lambda item: item["count"], reverse=True)
    if not people:
        say = f"I don't see commits on {path}."
    else:
        spoken = ", ".join(f"{item['name']} {item['count']}" for item in people[:5])
        say = f"On {path}: {spoken}."
    return {"path": path, "authors": people, "commits": commits, "say": say}


def _issue_number(query: str) -> int | None:
    match = re.search(r"#?(\d+)", query or "")
    if match and "#" in (query or ""):
        return int(match.group(1))
    if match and (query or "").strip().isdigit():
        return int(match.group(1))
    repo = _repo()
    raw = github_tools._request("GET", f"/repos/{repo}/commits", params={"per_page": 20})
    if not isinstance(raw, list):
        return None
    for commit in raw:
        message = ((commit.get("commit") or {}).get("message") or "")
        found = FIX_RE.search(message)
        if found:
            return int(found.group(1))
    return None


def _closing_pull(repo: str, number: int) -> int | None:
    try:
        events = github_tools._request("GET", f"/repos/{repo}/issues/{number}/timeline")
    except RuntimeError:
        events = []
    if not isinstance(events, list):
        return None
    for event in events:
        source = event.get("source") or {}
        issue = source.get("issue") or {}
        if issue.get("pull_request") and issue.get("number"):
            return int(issue["number"])
    return None


def explain_fix(query: str) -> dict:
    repo = _repo()
    number = _issue_number(query or "")
    if number is None:
        return {
            "say": "I need an issue number, like fixes number 12, before I walk a break to a fix.",
            "introduced": [],
            "fixed": [],
        }
    issue = github_tools._request("GET", f"/repos/{repo}/issues/{number}")
    pull_number = _closing_pull(repo, number)
    fixed = []
    introduced = []
    review = None
    if pull_number:
        pull = github_tools.get_pull_request(pull_number)
        fixed = pull.get("changed_files") or []
        diff = pull.get("diff") or ""
        try:
            review = jev_gate.review_change(pull.get("title") or f"#{number}", issue.get("body") or "", diff)
        except Exception as exc:
            review = {"error": str(exc)}
        if fixed:
            path = fixed[0]
            earlier = github_tools._request("GET", f"/repos/{repo}/commits", params={"path": path, "per_page": 5})
            if isinstance(earlier, list) and len(earlier) > 1:
                introduced = [path]
    say = f"Issue {number}: {issue.get('title') or 'untitled'}."
    if pull_number:
        say += f" Pull request {pull_number} touches {len(fixed)} files."
        verdict = ((review or {}).get("answers") or {}).get("verdict") or {}
        if verdict.get("choice"):
            say += f" Jev's verdict on that diff is {verdict['choice']}."
    else:
        say += " I cannot see a pull request that closed it, so I am not calling a root cause."
    return {
        "issue": number,
        "title": issue.get("title"),
        "pull": pull_number,
        "introduced": introduced,
        "fixed": fixed,
        "jev": review,
        "say": say,
    }


def read_thread(kind: str, number: int) -> dict:
    repo = _repo()
    number = int(number)
    kind = "pull" if kind == "pull" else "issue"
    item = github_tools._request("GET", f"/repos/{repo}/{'pulls' if kind == 'pull' else 'issues'}/{number}")
    comments = github_tools._request("GET", f"/repos/{repo}/issues/{number}/comments", params={"per_page": 30})
    reviews = []
    if kind == "pull":
        reviews = github_tools._request("GET", f"/repos/{repo}/pulls/{number}/comments", params={"per_page": 30})
    thread = []
    if item.get("body"):
        user = (item.get("user") or {}).get("login") or "unknown"
        thread.append({"author": user, "date": item.get("created_at"), "body": (item.get("body") or "")[:2000], "kind": kind})
    for comment in comments if isinstance(comments, list) else []:
        thread.append({
            "author": (comment.get("user") or {}).get("login") or "unknown",
            "date": comment.get("created_at"),
            "body": (comment.get("body") or "")[:2000],
            "kind": "comment",
        })
    for comment in reviews if isinstance(reviews, list) else []:
        thread.append({
            "author": (comment.get("user") or {}).get("login") or "unknown",
            "date": comment.get("created_at"),
            "body": (comment.get("body") or "")[:2000],
            "kind": "review",
        })
    title = item.get("title") or f"{kind} {number}"
    say = f"{title}. {len(thread)} posts in the thread."
    return {"kind": kind, "number": number, "title": title, "thread": thread, "say": say}


def _near_duplicate(titles: list[str]) -> bool:
    keys = [" ".join(title.lower().split()[:5]) for title in titles if title]
    return len(keys) >= 2 and len(set(keys)) < len(keys)


def scan_noise() -> dict:
    issues = github_tools.list_open_issues(30).get("issues") or []
    by_login: dict[str, list] = defaultdict(list)
    for issue in issues:
        by_login[issue.get("author") or "unknown"].append(issue)
    candidates = []
    for login, group in by_login.items():
        reasons = []
        if len(group) >= 3:
            reasons.append(f"{len(group)} open issues from {login}")
        if _near_duplicate([item.get("title") or "" for item in group]):
            reasons.append("near-duplicate titles")
        if not reasons:
            continue
        candidates.append({"login": login, "count": len(group), "reasons": reasons, "numbers": [item.get("number") for item in group]})
    scored = []
    for candidate in candidates[:5]:
        sample = next((item for item in issues if item.get("author") == candidate["login"]), None)
        noul = None
        if sample:
            try:
                judged = jev_gate.spam_signal(sample.get("title") or "", "")
                noul = ((judged.get("answers") or {}).get("spam") or {}).get("noul")
            except Exception:
                noul = None
        scored.append({**candidate, "spam_noul": noul})
    if not scored:
        say = "I don't see a burst of repeated issues in the open list."
    else:
        say = "Likely noise: " + "; ".join(f"{item['login']} ({item['count']})" for item in scored) + ". I did not close or hide anything."
    return {"candidates": scored, "say": say}
