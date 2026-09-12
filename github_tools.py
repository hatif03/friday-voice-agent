"""GitHub tools the agent can call, plus the OpenAI-style schemas that
describe them to the model.

Reads work on the active repo (GITHUB_REPO, or whichever repo the session
opened). create_issue and add_comment only stage a write. confirm_write
posts it after a later user turn says yes.
"""
import contextvars
import os
import re
import secrets
import time
from urllib.parse import urlencode

import requests

_turn_transcript_id: contextvars.ContextVar[str] = contextvars.ContextVar("turn_transcript_id", default="")
_turn_transcript: contextvars.ContextVar[str] = contextvars.ContextVar("turn_transcript", default="")


def set_turn_context(transcript_id: str, user_transcript: str) -> None:
    """Bind the latest human turn so a write cannot confirm itself."""
    _turn_transcript_id.set(transcript_id or "")
    _turn_transcript.set(user_transcript or "")

API_ROOT = "https://api.github.com"

_active_repo = None
_pending = None  # {"kind", "payload", "transcript_id"}
_session_login = None
_file_token = os.environ.get("GITHUB_TOKEN") or ""
_oauth_states: dict[str, float] = {}
OAUTH_CALLBACK = "http://127.0.0.1:5000/api/github/callback"


def set_active_repo(repo: str) -> str:
    """Remember owner/name for this process and for modules that read the env."""
    global _active_repo
    from map_pipeline import parse_github_ref

    ref = parse_github_ref(repo)
    slug = f"{ref['owner']}/{ref['repo']}"
    _active_repo = slug
    os.environ["GITHUB_REPO"] = slug
    return slug


def active_repo() -> str:
    return _active_repo or (os.environ.get("GITHUB_REPO") or "").strip()


def _repo() -> str:
    repo = active_repo()
    if not repo:
        raise RuntimeError("No repository is open. Name one like octocat/hello-world.")
    return repo


def connect_github(token: str) -> dict:
    """Hold a personal access token in this process. Return only the login."""
    global _session_login
    token = (token or "").strip()
    if not token:
        raise RuntimeError("Paste a GitHub token.")
    response = requests.get(
        f"{API_ROOT}/user",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "friday-voice-agent",
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError("GitHub rejected that token.")
    login = (response.json() or {}).get("login") or ""
    os.environ["GITHUB_TOKEN"] = token
    _session_login = login
    return {"connected": True, "login": login}


def disconnect_github() -> dict:
    """Drop the session token. A token loaded from the environment stays."""
    global _session_login
    os.environ["GITHUB_TOKEN"] = _file_token
    _session_login = None
    return {"connected": bool(_file_token.strip()), "login": None}


def github_status() -> dict:
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    client_id = (os.environ.get("GITHUB_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GITHUB_CLIENT_SECRET") or "").strip()
    return {
        "connected": bool(token),
        "login": _session_login,
        "source": "session" if _session_login else ("env" if token else "none"),
        "oauth": bool(client_id and client_secret),
    }


def oauth_callback_url() -> str:
    return (os.environ.get("GITHUB_OAUTH_CALLBACK") or OAUTH_CALLBACK).strip()


def begin_oauth() -> str:
    """Start GitHub's authorization-code flow. The secret never leaves the server."""
    client_id = (os.environ.get("GITHUB_CLIENT_ID") or "").strip()
    if not client_id or not (os.environ.get("GITHUB_CLIENT_SECRET") or "").strip():
        raise RuntimeError("GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET are not set.")
    now = time.time()
    stale = [key for key, expires in _oauth_states.items() if expires < now]
    for key in stale:
        _oauth_states.pop(key, None)
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = now + 600
    query = urlencode({
        "client_id": client_id,
        "redirect_uri": oauth_callback_url(),
        "scope": "repo read:org",
        "state": state,
    })
    return f"https://github.com/login/oauth/authorize?{query}"


def finish_oauth(code: str, state: str) -> dict:
    """Trade the one-time code for a token and keep that token on the server."""
    expires = _oauth_states.pop(state or "", None)
    if not expires or expires < time.time():
        raise RuntimeError("That GitHub sign-in expired. Start it again.")
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json", "User-Agent": "friday-voice-agent"},
        data={
            "client_id": (os.environ.get("GITHUB_CLIENT_ID") or "").strip(),
            "client_secret": (os.environ.get("GITHUB_CLIENT_SECRET") or "").strip(),
            "code": code,
            "redirect_uri": oauth_callback_url(),
        },
        timeout=30,
    )
    payload = response.json() if response.content else {}
    token = (payload or {}).get("access_token") or ""
    if not response.ok or not token:
        raise RuntimeError("GitHub did not finish sign-in.")
    return connect_github(token)


def list_accessible_repos(limit: int = 80) -> dict:
    """Repos the signed-in account owns, collaborates on, or can see through an org."""
    if not (os.environ.get("GITHUB_TOKEN") or "").strip():
        raise RuntimeError("Connect GitHub before listing repositories.")
    limit = max(1, min(int(limit or 80), 100))
    data = _request(
        "GET",
        "/user/repos",
        params={
            "per_page": limit,
            "sort": "updated",
            "affiliation": "owner,collaborator,organization_member",
        },
    )
    repos = []
    for repo in data if isinstance(data, list) else []:
        full = repo.get("full_name")
        if not full:
            continue
        repos.append({
            "full_name": full,
            "private": bool(repo.get("private")),
            "description": (repo.get("description") or "")[:140],
            "language": repo.get("language") or "",
        })
    return {"repos": repos}


def _headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "friday-voice-agent",
    }
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method: str, path: str, **kwargs) -> dict:
    response = requests.request(method, f"{API_ROOT}{path}", headers=_headers(), timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f"GitHub API {method} {path} failed ({response.status_code}): {response.text[:300]}")
    return response.json() if response.text else {}


def _request_text(path: str, accept: str) -> str:
    headers = _headers()
    headers["Accept"] = accept
    response = requests.get(f"{API_ROOT}{path}", headers=headers, timeout=60)
    if not response.ok:
        raise RuntimeError(f"GitHub API GET {path} failed ({response.status_code}): {response.text[:300]}")
    return response.text


def list_recent_commits(count: int = 5) -> dict:
    """List the most recent commits on the repo's default branch."""
    count = max(1, min(count, 20))
    data = _request("GET", f"/repos/{_repo()}/commits", params={"per_page": count})
    return {
        "commits": [
            {
                "sha": c["sha"][:10],
                "message": c["commit"]["message"].splitlines()[0],
                "author": (c["commit"]["author"] or {}).get("name"),
                "date": (c["commit"]["author"] or {}).get("date"),
                "url": c["html_url"],
            }
            for c in data
        ]
    }


def get_commit_diff(sha: str) -> dict:
    """Get the file-level diff for one commit, to see what actually changed."""
    data = _request("GET", f"/repos/{_repo()}/commits/{sha}")
    files = data.get("files", [])
    return {
        "sha": sha,
        "message": data.get("commit", {}).get("message", ""),
        "files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                # Truncate long patches so a big diff doesn't blow the context budget.
                "patch": (f.get("patch") or "")[:4000],
            }
            for f in files
        ],
    }


def list_open_issues(count: int = 10) -> dict:
    """List open issues (pull requests are excluded)."""
    count = max(1, min(count, 30))
    data = _request("GET", f"/repos/{_repo()}/issues", params={"state": "open", "per_page": count})
    return {
        "issues": [
            {
                "number": i["number"],
                "title": i["title"],
                "url": i["html_url"],
                "author": (i.get("user") or {}).get("login"),
                "created_at": i.get("created_at"),
            }
            for i in data
            if "pull_request" not in i
        ]
    }


def list_pull_requests(count: int = 5) -> dict:
    """List open pull requests."""
    count = max(1, min(count, 20))
    data = _request("GET", f"/repos/{_repo()}/pulls", params={"state": "open", "per_page": count})
    return {
        "pulls": [
            {
                "number": p["number"],
                "title": p["title"],
                "url": p["html_url"],
                "user": (p.get("user") or {}).get("login"),
            }
            for p in data
        ]
    }


def get_pull_request(number: int) -> dict:
    """Fetch a pull request title, body, and a trimmed unified diff."""
    data = _request("GET", f"/repos/{_repo()}/pulls/{number}")
    diff = _request_text(f"/repos/{_repo()}/pulls/{number}", "application/vnd.github.v3.diff")
    files = data.get("files") or []
    if not files:
        listed = _request("GET", f"/repos/{_repo()}/pulls/{number}/files", params={"per_page": 30})
        files = listed if isinstance(listed, list) else []
    return {
        "number": number,
        "title": data.get("title") or "",
        "body": (data.get("body") or "")[:4000],
        "url": data.get("html_url"),
        "diff": diff[:20000],
        "changed_files": [item.get("filename") for item in files if item.get("filename")],
    }


def _require_token() -> None:
    if not (os.environ.get("GITHUB_TOKEN") or "").strip():
        raise RuntimeError("GITHUB_TOKEN is not set, so Friday cannot write to GitHub.")


def _stage(kind: str, payload: dict, transcript_id: str) -> dict:
    global _pending
    _pending = {"kind": kind, "payload": payload, "transcript_id": transcript_id or ""}
    if kind == "issue":
        preview = payload.get("title") or ""
    else:
        preview = f"issue #{payload.get('issue_number')}"
    return {
        "status": "pending_confirmation",
        "kind": kind,
        "preview": preview,
        "say": (
            f"I drafted a {kind} ({preview}). I have not posted it. "
            "Say yes if you want it on GitHub."
        ),
    }


def create_issue(title: str, body: str = "", transcript_id: str = "") -> dict:
    """Stage a new GitHub issue. Nothing is posted until confirm_write."""
    title = (title or "").strip()
    if not title:
        raise RuntimeError("An issue needs a title.")
    return _stage("issue", {"title": title, "body": body or ""}, transcript_id or _turn_transcript_id.get())


def add_comment(issue_number: int, body: str, transcript_id: str = "") -> dict:
    """Stage a comment. Nothing is posted until confirm_write."""
    body = (body or "").strip()
    if not body:
        raise RuntimeError("A comment needs a body.")
    return _stage("comment", {"issue_number": int(issue_number), "body": body}, transcript_id or _turn_transcript_id.get())


_YES = re.compile(
    r"\b(yes|yeah|yep|yup|confirm|confirmed|do it|go ahead|post it|ship it|approve)\b",
    re.I,
)


def confirm_write(confirmed: bool = False, transcript_id: str = "", user_transcript: str = "") -> dict:
    """Post the staged write only after a later user turn that says yes."""
    global _pending
    transcript_id = transcript_id or _turn_transcript_id.get()
    user_transcript = user_transcript or _turn_transcript.get()
    if not confirmed:
        _pending = None
        return {"status": "cancelled", "say": "All right. I did not post anything."}
    if not _pending:
        return {"status": "nothing_pending", "say": "There is nothing waiting to post."}
    if transcript_id and transcript_id == _pending.get("transcript_id"):
        return {
            "status": "waiting",
            "say": "I still need you to say yes in your own words before I post that.",
        }
    if not _YES.search(user_transcript or ""):
        return {
            "status": "not_confirmed",
            "say": "I did not hear a yes, so I left it unposted.",
        }
    _require_token()
    pending = _pending
    _pending = None
    if pending["kind"] == "issue":
        data = _request("POST", f"/repos/{_repo()}/issues", json=pending["payload"])
        return {
            "status": "posted",
            "number": data["number"],
            "url": data["html_url"],
            "say": f"Posted issue {data['number']}. {data['html_url']}",
        }
    payload = pending["payload"]
    data = _request(
        "POST",
        f"/repos/{_repo()}/issues/{payload['issue_number']}/comments",
        json={"body": payload["body"]},
    )
    return {"status": "posted", "url": data["html_url"], "say": f"Posted the comment. {data['html_url']}"}


def pending_write() -> dict | None:
    return dict(_pending) if _pending else None


def looks_like_yes(text: str) -> bool:
    return bool(_YES.search(text or ""))


TOOL_FUNCTIONS = {
    "list_recent_commits": list_recent_commits,
    "get_commit_diff": get_commit_diff,
    "list_open_issues": list_open_issues,
    "list_pull_requests": list_pull_requests,
    "get_pull_request": get_pull_request,
    "create_issue": create_issue,
    "add_comment": add_comment,
    "confirm_write": confirm_write,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_recent_commits",
            "description": "List the most recent commits on the repo's default branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "How many commits to return (max 20).",
                        "default": 5,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_commit_diff",
            "description": "Get the file-level diff (patch) for one commit, to inspect what changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sha": {"type": "string", "description": "The commit SHA to inspect."}
                },
                "required": ["sha"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_issues",
            "description": "List currently open issues in the repo (pull requests excluded).",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "How many issues to return (max 30).",
                        "default": 10,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_issue",
            "description": (
                "Stage a new GitHub issue. This does NOT post it. After the user says yes "
                "in a later turn, call confirm_write. Look at the code before staging."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short issue title."},
                    "body": {
                        "type": "string",
                        "description": "Issue description — what was found and why it matters.",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_comment",
            "description": (
                "Stage a comment on an issue or pull request. This does NOT post it. "
                "After the user says yes in a later turn, call confirm_write."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_number": {
                        "type": "integer",
                        "description": "The issue or PR number to comment on.",
                    },
                    "body": {"type": "string", "description": "Comment text."},
                },
                "required": ["issue_number", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pull_requests",
            "description": "List open pull requests on the active repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "How many pull requests to return (max 20).", "default": 5}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pull_request",
            "description": "Fetch one pull request, including a trimmed diff, so it can be reviewed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer", "description": "Pull request number."}
                },
                "required": ["number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_write",
            "description": (
                "Post the staged issue or comment. Call this only after the user has said yes "
                "in a new turn. Never call it in the same turn that staged the write."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed": {
                        "type": "boolean",
                        "description": "True to post, false to discard the draft.",
                    }
                },
                "required": ["confirmed"],
            },
        },
    },
]
