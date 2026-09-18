"""Code-owned workflow for a spoken turn.

Navigation stays in code. Jev scores a change. The LLM Gateway drafts the
words. K2 and Vertex read the same evidence only when Jev says the question
is hard, and validate_review is the only way out.
"""
from concurrent.futures import ThreadPoolExecutor

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
    say = map_pipeline.landmark_brief(payload)
    return {
        "say": say,
        "ui_commands": [{"type": "load_map", "repo": payload["slug"]}],
        "result": {"repo": payload["slug"], "stats": payload["stats"], "landmarks": payload["landmarks"][:12], "say": say},
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
    return {
        "say": say,
        "ui_commands": [{"type": "focus", "path": path}],
        "result": {"path": path, "loc": meta["loc"], "kind": meta["kind"], "landmark": meta["landmark"], "say": say},
    }


def _list_landmarks(_arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    items = payload["landmarks"][:12]
    say = "Landmarks: " + ", ".join(item["path"] for item in items) if items else "No landmarks stood out."
    return {"say": say, "ui_commands": [], "result": {"landmarks": items, "say": say}}


def _set_layer(arguments: dict, _transcript: str) -> dict:
    layer = arguments.get("layer") or "heat"
    enabled = bool(arguments.get("enabled", True))
    say = f"{'Showing' if enabled else 'Hiding'} {layer}."
    return {"say": say, "ui_commands": [{"type": "layer", "layer": layer, "enabled": enabled}], "result": {"say": say}}


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
    review = jev_gate.review_change(title, body, diff)
    evidence = f"TITLE\n{title}\n\nFILES\n" + "\n".join(paths[:40]) + f"\n\nDIFF\n{diff[:12000]}"
    required = jev_gate.needs_second_reader(review)
    jobs = {"gateway": specialists.gateway_draft}
    if required:
        jobs["k2"] = specialists.k2_read
        jobs["vertex"] = specialists.vertex_read
    results = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {key: pool.submit(fn, evidence) for key, fn in jobs.items()}
        for key, future in futures.items():
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = {"source": key, "error": str(exc), "safe": False, "paths": []}
    draft = results.get("gateway") or {"source": "llm_gateway", "error": "missing", "safe": False, "paths": []}
    second = [results[key] for key in ("k2", "vertex") if key in results]
    known = set(payload["files"])
    for path in paths:
        known.add(path)
    gate = review_gate.validate_review(
        jev=review,
        draft=draft,
        known_paths=known,
        second_reads=second,
        second_reads_required=required,
    )
    judgment = {
        "title": title,
        "sha": sha,
        "pr_number": number,
        "paths": paths,
        "jev": review,
        "draft": {"summary": draft.get("summary"), "safe": draft.get("safe"), "source": "llm_gateway"},
        "second_reads": [{"source": item.get("source"), "safe": item.get("safe"), "error": item.get("error"), "summary": item.get("summary")} for item in second],
        "gate": gate,
    }
    commands = [{"type": "judgment", "judgment": judgment}, {"type": "heat_paths", "paths": paths}]
    if paths:
        commands.append({"type": "focus", "path": paths[0]})
    trace = [
        {"step": "jev", "detail": "review", "answers": (review or {}).get("answers")},
        {"step": "readers", "detail": "gateway" + ("+k2+vertex" if required else ""), "required": required},
        {"step": "gate", "detail": gate.get("say"), "cleared": gate.get("cleared"), "reasons": gate.get("reasons")},
    ]
    return {
        "say": gate["say"],
        "ui_commands": commands,
        "trace": trace,
        "result": {"say": gate["say"], "cleared": gate["cleared"], "tone": gate["tone"], "verdict": gate["verdict"]},
    }


def _explain_architecture(_arguments: dict, _transcript: str) -> dict:
    payload = _require_map()
    listing = "\n".join(list(payload["files"])[:400])
    readme = ""
    if payload.get("readme_path"):
        readme = payload["readme_path"]
    graph = specialists.gateway_graph(listing, readme)
    filtered = specialists.filter_graph(graph, set(payload["files"]))
    critique = specialists.vertex_read(
        "Critique this architecture summary. " + (filtered.get("summary") or "") + "\nNodes:\n"
        + "\n".join(node["path"] for node in filtered["nodes"])
    )
    disagree = critique.get("safe") is False and "error" not in critique
    say = filtered.get("summary") or "I could not draw an architecture graph from the files in view."
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
        return {"say": say, "ui_commands": [], "result": result if isinstance(result, dict) else {"value": result}}
    return handler


def _plain(name: str, result: dict) -> str:
    if name == "list_recent_commits":
        commits = result.get("commits") or []
        if not commits:
            return "No commits came back."
        return "Latest commit: " + commits[0].get("message", "")
    if name == "list_open_issues":
        issues = result.get("issues") or []
        return f"{len(issues)} open issues." if issues else "No open issues."
    if name == "list_pull_requests":
        pulls = result.get("pulls") or []
        return f"{len(pulls)} open pull requests." if pulls else "No open pull requests."
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
        raise RuntimeError("Name a file.")
    if path not in payload["files"]:
        matches = [item for item in payload["files"] if item.endswith("/" + path) or item.endswith(path)]
        if len(matches) == 1:
            path = matches[0]
    found = history.who_touched(path)
    return {
        "say": found["say"],
        "ui_commands": [{"type": "authors", "authors": found}, {"type": "focus", "path": path}],
        "trace": [{"step": "authors", "detail": found["say"]}],
        "result": found,
    }


def _explain_fix(arguments: dict, _transcript: str) -> dict:
    _require_map()
    found = history.explain_fix(arguments.get("query") or arguments.get("issue") or "")
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
    _require_map()
    kind = arguments.get("kind") or "issue"
    number = arguments.get("number")
    if not number:
        raise RuntimeError("Name an issue or pull request number.")
    found = history.read_thread(kind, int(number))
    return {
        "say": found["say"],
        "ui_commands": [{"type": "thread", "thread": found}],
        "trace": [{"step": "thread", "detail": found["say"]}],
        "result": {"say": found["say"], "posts": len(found["thread"])},
    }


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
    "set_map_layer": _set_layer,
    "review_changes": _review_changes,
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
}
