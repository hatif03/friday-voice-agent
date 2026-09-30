"""Code-owned workflow for a spoken turn.

Jev decides when it is confident. Gemini decides only when Jev is unsure,
and K2 runs only if Gemini fails. AssemblyAI phrases that decision.
validate_review is the only way out.
"""
from github_tools import (
    active_repo,
    add_comment,
    confirm_write,
    create_issue,
    get_commit_diff,
    get_pull_request,
    list_open_issues,
    list_pull_requests,
    list_recent_commits,
    set_active_repo,
    set_turn_context,
)
import history
import jev_gate
import map_pipeline
import review_gate
import specialists


def _safe_args(arguments: dict) -> dict:
    clean = {}
    for key, value in (arguments or {}).items():
        if any(word in key.lower() for word in ("token", "secret", "password", "key")):
            continue
        clean[key] = str(value)[:400]
    return clean


def dispatch(name: str, arguments: dict, user_transcript: str = "", transcript_id: str = "") -> dict:
    set_turn_context(transcript_id, user_transcript)
    arguments = dict(arguments or {})
    arguments.pop("transcript_id", None)
    arguments.pop("user_transcript", None)
    handler = _HANDLERS.get(name)
    header = {"step": "tool", "name": name, "arguments": _safe_args(arguments)}
    if handler is None:
        return {
            "say": f"I don't have a tool named {name}.",
            "ui_commands": [],
            "result": {"error": "unknown tool", "say": f"I don't have a tool named {name}."},
            "is_error": True,
            "trace": [header],
        }
    try:
        outcome = handler(arguments, user_transcript)
    except Exception as exc:
        return {
            "say": f"That failed. {exc}",
            "ui_commands": [],
            "result": {"error": str(exc)},
            "is_error": True,
            "trace": [header, {"step": "error", "detail": str(exc)}],
        }
    outcome.setdefault("trace", [])
    outcome["trace"].insert(0, header)
    return outcome


def _open_repository(arguments: dict, _transcript: str) -> dict:
    slug = arguments.get("repo") or ""
    if arguments.get("owner") and arguments.get("name"):
        slug = f"{arguments['owner']}/{arguments['name']}"
    set_active_repo(slug)
    payload = map_pipeline.open_repo(slug)
    attention = {}
    try:
        paths = [item["path"] for item in payload["landmarks"][:12]]
        attention = jev_gate.choose_landmark(paths)
    except Exception as exc:
        attention = {"error": str(exc)}
    choice = ((attention.get("answers") or {}).get("open_first") or {}).get("choice")
    brief = map_pipeline.landmark_brief(payload)
    if choice:
        brief += f" Jev would open {choice} first."
    commands = [
        {"type": "load_map", "repo": payload["slug"]},
        {"type": "keyterms", "keyterms": payload["keyterms"]},
    ]
    trace = [{"step": "jev", "detail": "landmark choice", "open_first": choice}]
    if payload.get("focus_path"):
        commands.append({"type": "focus", "path": payload["focus_path"]})
        brief += f" Focusing {payload['focus_path']}."
    if payload.get("pull_number"):
        review = _review_changes({"pr_number": payload["pull_number"]}, _transcript)
        commands.extend(review.get("ui_commands") or [])
        brief = review.get("say") or brief
        trace.extend(review.get("trace") or [])
    return {
        "say": brief,
        "ui_commands": commands,
        "trace": trace,
        "result": {
            "repo": payload["slug"],
            "stats": payload["stats"],
            "landmarks": payload["landmarks"][:12],
            "open_first": choice,
            "focus_path": payload.get("focus_path"),
            "pull_number": payload.get("pull_number"),
            "say": brief,
        },
    }


def _home(payload: dict) -> str:
    owner, repo = payload.get("owner"), payload.get("repo")
    if owner and repo:
        return f"https://github.com/{owner}/{repo}"
    return ""


def _blob(payload: dict, path: str) -> str:
    home = _home(payload)
    branch = payload.get("branch")
    if home and path and branch:
        return f"{home}/blob/{branch}/{path}"
    return home


def _link(label: str, url: str) -> str:
    text = str(label or "").replace("[", "").replace("]", "")
    if url and str(url).startswith("https://"):
        return f"[{text}]({url})"
    return text


def _with_link(say: str, url: str, label: str = "") -> str:
    if not url:
        return say
    return f"{say} {_link(label or url, url)}."


def _require_map() -> dict:
    slug = active_repo()
    if not slug:
        raise RuntimeError("No repository is open yet.")
    cached = map_pipeline.get_cached(slug)
    if cached:
        return cached
    return map_pipeline.open_repo(slug)


def _describe_map(_arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    say = _with_link(map_pipeline.explain_map(payload), _home(payload), payload.get("slug") or "GitHub")
    stats = payload.get("stats") or {}
    return {
        "say": say,
        "ui_commands": [{"type": "load_map", "repo": payload["slug"]}],
        "trace": [{"step": "map", "detail": f"{payload['slug']}: {stats.get('files', 0)} files, {stats.get('loc', 0)} lines"}],
        "result": {"repo": payload["slug"], "stats": payload["stats"], "landmarks": payload["landmarks"][:12], "say": say},
    }


def _resolve_path(payload: dict, hint: str) -> str:
    hint = (hint or "").strip()
    files = payload.get("files") or {}
    if hint in files:
        return hint
    if not hint:
        return ""
    matches = [path for path in files if path.endswith("/" + hint) or path.endswith(hint)]
    if len(matches) == 1:
        return matches[0]
    return ""


def _explain_project(_arguments: dict, transcript: str) -> dict:
    """Read the README and a few real files, then say what the project is."""
    payload = _require_map()
    import ask
    import chat

    found = ask.explain_repository(transcript, payload, list(chat._TURNS))
    say = found.get("say") or "I can't find an explanation of this project in the files on this map."
    paths = found.get("paths") or []
    linked = [_link(path, _blob(payload, path)) for path in paths[:6]]
    linked = [item for item in linked if item.startswith("[")]
    if linked:
        say = say.rstrip() + "\n\n" + " · ".join(linked)
    return {
        "say": say,
        "ui_commands": [],
        "trace": [{"step": "files", "detail": ", ".join(paths) or "no file text", "paths": paths}],
        "result": {"say": say, "spoken": found.get("spoken") or say, "paths": paths},
    }


def _explain_file(arguments: dict, transcript: str) -> dict:
    """Say what the file does from its cached source. Do not answer with size alone."""
    payload = _require_map()
    import chat

    path = _resolve_path(payload, arguments.get("path") or "") or chat.focused()
    path = _resolve_path(payload, path)
    if not path:
        say = "I can't find that file in this repository."
        return {"say": say, "ui_commands": [], "trace": [{"step": "explain_file", "detail": say}], "result": {"say": say}}
    text = ((payload.get("source_text") or {}).get(path) or "").strip()
    if not text:
        say = f"I can't find the source of {path} in this repository."
        return {
            "say": say,
            "ui_commands": [{"type": "focus", "path": path}],
            "trace": [{"step": "explain_file", "detail": path}],
            "result": {"say": say, "path": path},
        }
    import ask

    summary = ask.explain_source(path, text)
    if not summary:
        say = f"I can't find an explanation of {path} in the source on this map."
    else:
        say = summary
    link = _link(path, _blob(payload, path))
    say = f"**{link}**\n\n{say}" if link.startswith("[") else f"**{path}**\n\n{say}"
    chat.note_focus(path)
    return {
        "say": say,
        "ui_commands": [{"type": "focus", "path": path}],
        "trace": [{"step": "explain_file", "detail": path}],
        "result": {"say": say, "path": path},
    }


def _give_up(_arguments: dict, _transcript: str) -> dict:
    say = "I can't find that in this repository."
    return {"say": say, "ui_commands": [], "trace": [{"step": "give_up", "detail": say}], "result": {"say": say}}


def _friday_turn(arguments: dict, transcript: str) -> dict:
    import chat

    utterance = arguments.get("utterance") or transcript or ""
    found = chat.turn(utterance)
    return {
        "say": found["say"],
        "ui_commands": found.get("ui_commands") or [],
        "trace": found.get("steps") or [],
        "result": {"say": found["say"], "paths": found.get("paths") or []},
    }


def _focus_file(arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    path = (arguments.get("path") or "").strip()
    meta = payload["files"].get(path)
    if meta is None:
        matches = [item for item in payload["files"] if item.endswith("/" + path) or item.endswith(path)]
        if len(matches) == 1:
            path = matches[0]
            meta = payload["files"][path]
    if meta is None:
        say = f"I can't see {path} on this map."
        return {"say": say, "ui_commands": [], "is_error": True, "result": {"error": "not on map", "say": say}}
    flags = [name for name, on in meta["landmark"].items() if on]
    say = f"{path}, {meta['loc']} lines, kind {meta['kind']}."
    if flags:
        say += " Marked as " + ", ".join(flags) + "."
    if meta["imported_by"]:
        say += f" Imported by {len(meta['imported_by'])} files."
    say = _with_link(say, _blob(payload, path), path)
    return {
        "say": say,
        "ui_commands": [{"type": "focus", "path": path}],
        "result": {"path": path, "loc": meta["loc"], "kind": meta["kind"], "landmark": meta["landmark"], "say": say},
    }


def _explain_landmarks(_arguments: dict, _transcript: str) -> dict:
    """Say what each landmark file does. A list of paths is not an explanation."""
    payload = _require_map()
    import ask

    items = (payload.get("landmarks") or [])[:12]
    if not items:
        say = "No landmarks stood out."
        home = _home(payload)
        if home:
            say = _with_link(say, home, payload.get("slug") or "GitHub")
        return {"say": say, "ui_commands": [], "result": {"say": say, "spoken": say, "paths": []}}
    rows = {row.get("path"): (row.get("sentence") or "").strip() for row in (ask.explain_landmarks(payload) or [])}
    lines = []
    spoken = []
    paths = []
    for item in items:
        path = item.get("path") or ""
        if not path:
            continue
        paths.append(path)
        sentence = (rows.get(path) or "I can't find an explanation of this file in the source on this map.").rstrip(".")
        lines.append(f"**{_link(path, _blob(payload, path))}**\n\n{sentence}.")
        spoken.append(f"{sentence}.")
    say = "\n\n".join(lines)
    voice = " ".join(spoken)
    return {
        "say": say,
        "ui_commands": [{"type": "highlight", "paths": paths}],
        "trace": [{"step": "explain_landmarks", "detail": ", ".join(paths), "paths": paths}],
        "result": {"say": say, "spoken": voice, "paths": paths},
    }


def _list_landmarks(_arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    items = payload["landmarks"][:12]
    if items:
        say = "Landmarks\n\n" + "\n".join(
            f"- {_link(item['path'], _blob(payload, item['path']))}" for item in items
        )
    else:
        say = "No landmarks stood out."
        home = _home(payload)
        if home:
            say = _with_link(say, home, payload.get("slug") or "GitHub")
    return {"say": say, "ui_commands": [], "result": {"landmarks": items, "say": say}}


def _set_layer(arguments: dict, _transcript: str) -> dict:
    layer = arguments.get("layer") or "heat"
    enabled = bool(arguments.get("enabled", True))
    say = f"{'Showing' if enabled else 'Hiding'} {layer}."
    return {"say": say, "ui_commands": [{"type": "layer", "layer": layer, "enabled": enabled}], "result": {"say": say}}


def _ask_reader(fn, evidence: str, source: str) -> dict:
    try:
        result = fn(evidence)
    except Exception as exc:
        return {"source": source, "error": str(exc), "safe": False, "paths": [], "summary": ""}
    if not isinstance(result, dict):
        return {"source": source, "error": "empty response", "safe": False, "paths": [], "summary": ""}
    result.setdefault("source", source)
    return result


def _decision_brief(review: dict, decision_route: str, reader, decided_by: str) -> str:
    answers = (review or {}).get("answers") or {}
    verdict = answers.get("verdict") or {}
    if decision_route == "accept":
        lines = [
            "route: accept",
            "decided_by: jev",
            f"verdict: {verdict.get('choice')}",
            f"confidence: {verdict.get('confidence')}",
        ]
        for key, value in answers.items():
            if key != "verdict":
                lines.append(f"{key}: {value}")
        lines.append("Phrase this verdict and the rubric. Do not change the verdict.")
        return "\n".join(lines)
    concerns = (reader or {}).get("concerns") or []
    return (
        "route: escalate\n"
        f"decided_by: {decided_by}\n"
        f"safe: {(reader or {}).get('safe')}\n"
        f"summary: {(reader or {}).get('summary') or ''}\n"
        f"concerns: {concerns}\n"
        "Phrase this reader's summary and concerns. Do not change the decision."
    )


def judge_change(title: str, body: str, diff: str, paths: list, known_paths: set) -> dict:
    """Accept a confident Jev verdict. Otherwise Gemini decides, then K2 if Gemini errors."""
    review = jev_gate.review_change(title, body, diff)
    decision_route = jev_gate.route(review)
    evidence = f"TITLE\n{title}\n\nFILES\n" + "\n".join(paths[:40]) + f"\n\nDIFF\n{diff[:12000]}"
    reader = None
    decided_by = "jev"
    if decision_route == "escalate":
        reader = _ask_reader(specialists.vertex_read, evidence, "vertex")
        decided_by = "vertex"
        if reader.get("error"):
            reader = _ask_reader(specialists.k2_read, evidence, "k2")
            decided_by = "k2"
    brief = _decision_brief(review, decision_route, reader, decided_by)
    try:
        draft = specialists.gateway_phrase(evidence + "\n\nDECISION\n" + brief)
    except Exception as exc:
        draft = {"source": "llm_gateway", "error": str(exc), "summary": "", "paths": []}
    if not isinstance(draft, dict):
        draft = {"source": "llm_gateway", "error": "empty phrase", "summary": "", "paths": []}
    gate = review_gate.validate_review(
        jev=review,
        draft=draft,
        known_paths=known_paths,
        route=decision_route,
        reader=reader,
    )
    return {
        "review": review,
        "route": decision_route,
        "decided_by": decided_by,
        "reader": reader,
        "draft": draft,
        "gate": gate,
    }


def _review_changes(arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    number = arguments.get("pr_number") or arguments.get("number")
    sha = arguments.get("sha")
    if number:
        pr = get_pull_request(int(number))
        title, body, diff = pr["title"], pr["body"], pr["diff"]
        paths = pr.get("changed_files") or []
    else:
        if not sha:
            commits = list_recent_commits(1)
            if not commits["commits"]:
                return {"say": "This repository has no commits I can see.", "ui_commands": [], "result": {}}
            sha = commits["commits"][0]["sha"]
        commit = get_commit_diff(sha)
        title = commit.get("message") or sha
        body = ""
        diff = "\n".join(
            f"FILE {item.get('filename')}\n{item.get('patch') or ''}" for item in commit.get("files") or []
        )
        paths = [item.get("filename") for item in commit.get("files") or [] if item.get("filename")]
    known = set(payload["files"])
    for path in paths:
        known.add(path)
    judged = judge_change(title, body, diff, paths, known)
    review = judged["review"]
    draft = judged["draft"]
    reader = judged["reader"]
    gate = judged["gate"]
    judgment = {
        "title": title,
        "sha": sha,
        "pr_number": number,
        "paths": paths,
        "jev": review,
        "route": judged["route"],
        "decided_by": judged["decided_by"],
        "draft": {"summary": draft.get("summary"), "source": "llm_gateway"},
        "reader": (
            {"source": reader.get("source"), "safe": reader.get("safe"), "error": reader.get("error"), "summary": reader.get("summary")}
            if reader
            else None
        ),
        "gate": gate,
    }
    commands = [{"type": "judgment", "judgment": judgment}, {"type": "heat_paths", "paths": paths}]
    if paths:
        commands.append({"type": "focus", "path": paths[0]})
    trace = [
        {"step": "jev", "detail": judged["route"], "answers": (review or {}).get("answers")},
        {"step": "decision", "detail": judged["decided_by"], "route": judged["route"]},
        {"step": "gate", "detail": gate.get("say"), "cleared": gate.get("cleared"), "reasons": gate.get("reasons")},
    ]
    say = gate["say"]
    if number:
        say = _with_link(say, f"{_home(payload)}/pull/{number}", f"pull {number}")
    elif sha:
        say = _with_link(say, f"{_home(payload)}/commit/{sha}", sha)
    return {
        "say": say,
        "ui_commands": commands,
        "trace": trace,
        "result": {"say": say, "cleared": gate["cleared"], "tone": gate["tone"], "verdict": gate["verdict"]},
    }


def _latest_change(_arguments: dict, _transcript: str) -> dict:
    """Say what the newest commit changed, from GitHub, not from the map."""
    _require_map()
    commits = list_recent_commits(1).get("commits") or []
    if not commits:
        say = "This repository has no commits I can see."
        return {"say": say, "ui_commands": [], "result": {"say": say}}
    commit = commits[0]
    diff = get_commit_diff(commit["sha"])
    files = [item.get("filename") for item in diff.get("files") or [] if item.get("filename")]
    shown = ", ".join(files[:8])
    if shown:
        say = f"Latest commit {commit['sha']}: {commit.get('message') or ''}. Changed {len(files)} files: {shown}."
    else:
        say = f"Latest commit {commit['sha']}: {commit.get('message') or ''}. GitHub did not list changed files."
    say = _with_link(say, commit.get("url") or "", commit["sha"])
    commands = [{"type": "focus", "path": files[0]}] if files else []
    return {"say": say, "ui_commands": commands, "trace": [{"step": "commit", "detail": commit["sha"], "paths": files}], "result": {"say": say, "paths": files}}


def _explain_architecture(_arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    listing = "\n".join(list(payload["files"])[:400])
    readme = ""
    for path, text in (payload.get("source_text") or {}).items():
        if path.lower().endswith("readme.md") or path.lower().endswith("readme.rst"):
            readme = text
            break
    try:
        graph = specialists.gateway_graph(listing, readme)
    except Exception:
        graph = {"summary": "", "groups": [], "nodes": [], "edges": []}
    filtered = specialists.filter_graph(graph, set(payload["files"]))
    try:
        critique = specialists.vertex_read(
            "Critique this architecture summary. " + (filtered.get("summary") or "") + "\nNodes:\n"
            + "\n".join(node["path"] for node in filtered["nodes"])
        )
    except Exception as exc:
        critique = {"error": str(exc), "safe": False, "paths": []}
    disagree = critique.get("safe") is False and "error" not in critique
    say = filtered.get("summary") or ""
    if not say:
        import ask

        found = ask.explain_repository("How do the pieces of this repository fit together?", payload, [])
        say = found.get("say") or "I could not draw an architecture graph from the files in view."
    if disagree:
        say = "Vertex does not fully agree with that picture. " + say + " " + (critique.get("summary") or "")
    mermaid = specialists.graph_to_mermaid(filtered)
    return {
        "say": say,
        "ui_commands": [{"type": "architecture", "mermaid": mermaid, "summary": say}],
        "result": {"say": say, "nodes": len(filtered["nodes"]), "disagree": disagree},
    }


def _passthrough(fn):
    def handler(arguments: dict, _transcript: str) -> dict:
        result = fn(**arguments)
        say = result.get("say") if isinstance(result, dict) else None
        if not say:
            say = _plain(fn.__name__, result)
        commands = []
        if isinstance(result, dict) and result.get("status") == "needs_github":
            commands.append({"type": "connect_github"})
        return {
            "say": say,
            "ui_commands": commands,
            "result": result if isinstance(result, dict) else {"value": result},
        }
    return handler


def _plain(name: str, result: dict) -> str:
    if name == "list_recent_commits":
        commits = result.get("commits") or []
        if not commits:
            return "No commits came back."
        if len(commits) == 1:
            commit = commits[0]
            return "Latest commit: " + _link(commit.get("sha") or "commit", commit.get("url")) + " " + commit.get("message", "")
        bits = [
            _link(item.get("sha") or "commit", item.get("url")) + " " + (item.get("message") or "")
            for item in commits[:8]
        ]
        return f"{len(commits)} recent commits: " + "; ".join(bits) + "."
    if name == "list_open_issues":
        issues = result.get("issues") or []
        if not issues:
            return "GitHub reports no open issues."
        bits = [_link(f"#{item.get('number')} {item.get('title')}", item.get("url")) for item in issues[:5]]
        return f"{len(issues)} open issues from GitHub: " + "; ".join(bits) + "."
    if name == "list_pull_requests":
        pulls = result.get("pulls") or []
        if not pulls:
            return "GitHub reports no open pull requests."
        bits = [_link(f"#{item.get('number')} {item.get('title')}", item.get("url")) for item in pulls[:5]]
        return f"{len(pulls)} open pull requests from GitHub: " + "; ".join(bits) + "."
    return "Done."


def _scrub_history(arguments: dict, _transcript: str) -> dict:
    _require_map()
    window = history.load_window(int(arguments.get("count") or 30))
    index = arguments.get("index")
    paths = []
    if index is not None and window["commits"]:
        chosen = window["commits"][max(0, min(int(index), len(window["commits"]) - 1))]
        paths = chosen.get("files") or []
        window["say"] = f"{chosen['author']}, {chosen['date'] or ''}. {chosen['message']}"
    elif arguments.get("play"):
        paths = []
        for commit in window["commits"][:10]:
            paths.extend(commit.get("files") or [])
        window["say"] = "Playing the latest commits on the map. " + window["say"]
    return {
        "say": window["say"],
        "ui_commands": [{"type": "history", "history": window, "paths": paths}],
        "trace": [{"step": "history", "detail": window["say"]}],
        "result": {"say": window["say"], "commits": len(window["commits"]), "contributors": window["contributors"]},
    }


def _who_touched(arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    path = (arguments.get("path") or "").strip()
    if not path:
        say = "Name a file, or focus one first."
        return {"say": say, "ui_commands": [], "result": {"say": say}}
    if path not in payload["files"]:
        matches = [item for item in payload["files"] if item.endswith("/" + path) or item.endswith(path)]
        if len(matches) == 1:
            path = matches[0]
    found = history.who_touched(path)
    return {
        "say": _with_link(found["say"], _blob(payload, path), path),
        "ui_commands": [{"type": "authors", "authors": found}, {"type": "focus", "path": path}],
        "trace": [{"step": "authors", "detail": found["say"]}],
        "result": found,
    }


def _explain_fix(arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    found = history.explain_fix(arguments.get("query") or arguments.get("issue") or "")
    if found.get("pull"):
        found["say"] = _with_link(found.get("say") or "", f"{_home(payload)}/pull/{found['pull']}", f"pull {found['pull']}")
    elif found.get("issue"):
        found["say"] = _with_link(found.get("say") or "", f"{_home(payload)}/issues/{found['issue']}", f"issue {found['issue']}")
    commands = [{"type": "fix", "fix": found}]
    if found.get("introduced"):
        commands.append({"type": "highlight", "paths": found["introduced"], "tone": "introduced"})
    if found.get("fixed"):
        commands.append({"type": "highlight", "paths": found["fixed"], "tone": "fixed"})
    return {
        "say": found["say"],
        "ui_commands": commands,
        "trace": [{"step": "fix", "detail": found["say"], "jev": found.get("jev")}],
        "result": {"say": found["say"], "issue": found.get("issue"), "pull": found.get("pull")},
    }


def _read_thread(arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    kind = arguments.get("kind") or "issue"
    number = int(arguments.get("number") or 0)

    def pack(found: dict) -> dict:
        kind_name = "pull" if (found.get("kind") == "pull") else "issues"
        number = found.get("number")
        home = _home(payload)
        url = f"{home}/{'pull' if kind_name == 'pull' else 'issues'}/{number}" if home and number else ""
        found["say"] = _with_link(found.get("say") or "", url, f"#{number}" if number else "GitHub")
        return {
            "say": found["say"],
            "ui_commands": [{"type": "thread", "thread": found}],
            "trace": [{"step": "thread", "detail": found["say"]}],
            "result": {"say": found["say"], "posts": len(found.get("thread") or [])},
        }

    if number:
        try:
            return pack(history.read_thread(kind, number))
        except Exception:
            pass
    issues = list_open_issues(10).get("issues") or []
    if not issues:
        say = f"Issue {number} is not there, and GitHub reports no open issues." if number else "GitHub reports no open issues."
        return {"say": say, "ui_commands": [], "trace": [{"step": "thread", "detail": say}], "result": {"say": say}}
    newest = issues[0]
    try:
        found = history.read_thread("issue", int(newest["number"]))
    except Exception:
        say = f"Issue {number} is not there. The newest open issue is #{newest.get('number')} {newest.get('title')}."
        return {"say": say, "ui_commands": [], "trace": [{"step": "thread", "detail": say}], "result": {"say": say}}
    prefix = f"Issue {number} is not there. " if number else ""
    found["say"] = prefix + f"The newest open issue is #{found.get('number')}. {found.get('say')}"
    return pack(found)


def _scan_security(_arguments: dict, _transcript: str) -> dict:
    _require_map()
    import security

    found = security.scan_open()
    return {
        "say": found["say"],
        "ui_commands": [{"type": "security", "security": found}],
        "trace": [{"step": "security", "detail": found["say"], "findings": found["findings"]}],
        "result": {"say": found["say"], "count": len(found["findings"])},
    }


def _ask_repository(arguments: dict, transcript: str) -> dict:
    _require_map()
    import ask

    question = arguments.get("question") or transcript or ""
    found = ask.answer(question)
    return {
        "say": found["say"],
        "ui_commands": [{"type": "highlight", "paths": found["paths"]}, {"type": "ask", "ask": found}],
        "trace": found["steps"],
        "result": {"say": found["say"], "paths": found["paths"]},
    }


def _scan_noise(_arguments: dict, _transcript: str) -> dict:
    _require_map()
    found = history.scan_noise()
    return {
        "say": found["say"],
        "ui_commands": [{"type": "noise", "noise": found}],
        "trace": [{"step": "noise", "detail": found["say"], "candidates": found["candidates"]}],
        "result": {"say": found["say"], "count": len(found["candidates"])},
    }


_HANDLERS = {
    "open_repository": _open_repository,
    "describe_map": _describe_map,
    "focus_file": _focus_file,
    "list_landmarks": _list_landmarks,
    "explain_landmarks": _explain_landmarks,
    "set_map_layer": _set_layer,
    "review_changes": _review_changes,
    "latest_change": _latest_change,
    "explain_architecture": _explain_architecture,
    "list_recent_commits": _passthrough(list_recent_commits),
    "list_open_issues": _passthrough(list_open_issues),
    "list_pull_requests": _passthrough(list_pull_requests),
    "create_issue": _passthrough(create_issue),
    "add_comment": _passthrough(add_comment),
    "confirm_write": _passthrough(confirm_write),
    "scrub_history": _scrub_history,
    "who_touched": _who_touched,
    "explain_fix": _explain_fix,
    "read_thread": _read_thread,
    "scan_noise": _scan_noise,
    "scan_security": _scan_security,
    "ask_repository": _ask_repository,
    "explain_project": _explain_project,
    "explain_file": _explain_file,
    "give_up": _give_up,
    "friday_turn": _friday_turn,
}
