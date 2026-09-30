"""One turn for typed and spoken questions.

Unambiguous requests (the map, a named GitHub list, a later yes) run directly.
Multi-step GitHub triage can use the AssemblyAI Gateway tool loop (agent.py).
Jev chooses the tool for map/repo work.
K2 chooses only when that confidence is under 0.9. The spoken line is the tool's say,
or an honest stop.
"""
import os
import re
import uuid

import github_tools
import jev_gate
import map_pipeline
import specialists

_TURNS = []
_FOCUS = None
_PENDING_COMMENT_ON = 0
_PENDING_ISSUE_AWAITING = None  # "title" while waiting for a name after need_issue_title
GIVE_UP = "I can't find that in this repository."


def reset() -> None:
    global _FOCUS, _PENDING_COMMENT_ON, _PENDING_ISSUE_AWAITING
    _TURNS.clear()
    _FOCUS = None
    _PENDING_COMMENT_ON = 0
    _PENDING_ISSUE_AWAITING = None


def _set_pending_issue_title() -> None:
    global _PENDING_ISSUE_AWAITING
    _PENDING_ISSUE_AWAITING = "title"


def _clear_pending_issue() -> None:
    global _PENDING_ISSUE_AWAITING
    _PENDING_ISSUE_AWAITING = None


def _set_pending_comment(number: int) -> None:
    global _PENDING_COMMENT_ON
    _PENDING_COMMENT_ON = int(number) if number else 0


def note_focus(path: str) -> None:
    global _FOCUS
    if path:
        _FOCUS = path


def focused() -> str:
    return _FOCUS or ""


def _remember(user: str, say: str) -> None:
    _TURNS.append({"user": user, "say": say})
    del _TURNS[:-8]


def _state(payload: dict, utterance: str) -> str:
    lines = [f"Repository {payload.get('slug') or github_tools.active_repo()}"]
    if _FOCUS:
        lines.append(f"Focused file: {_FOCUS}")
    for turn in _TURNS[-8:]:
        lines.append(f"User: {turn['user']}")
        lines.append(f"Friday: {(turn.get('say') or '')[:300]}")
    lines.append(f"Utterance: {utterance}")
    return "\n".join(lines)


def _asks_about_project(text: str) -> bool:
    if re.search(r"\b(file|function|class)\b", text or "", re.I):
        return False
    return bool(re.search(r"\b(project|repo|repository|codebase|overview)\b", text or "", re.I)) and bool(
        re.search(r"\b(explain|what|about|describe|summar|overview|tell|does|do|is)\b", text or "", re.I)
    )


def _asks_what_it_does(text: str) -> bool:
    if re.search(r"\b(project|repo|repository|codebase)\b", text or "", re.I):
        return False
    return bool(re.search(r"\b(do|does|purpose|work|explain)\b", text, re.I)) and bool(
        re.search(r"\b(file|this|it|code)\b", text, re.I)
    )


def _named_repo(text: str) -> str:
    match = re.search(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b", text or "")
    if not match:
        return ""
    return f"{match.group(1)}/{match.group(2)}"


def _named_path(text: str, files: dict) -> str:
    for token in re.findall(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+", text or ""):
        if token in files:
            return token
        matches = [path for path in files if path.endswith("/" + token) or path.endswith(token)]
        if len(matches) == 1:
            return matches[0]
    return ""


def _arguments(name: str, utterance: str, payload: dict) -> dict:
    files = payload.get("files") or {}
    path = _named_path(utterance, files) or _FOCUS or ""
    if name in {"explain_file", "focus_file", "who_touched"}:
        return {"path": path}
    if name == "read_thread":
        match = re.search(r"#(\d+)|\b(\d+)\b", utterance)
        number = int(next(group for group in match.groups() if group)) if match else 0
        kind = "pull" if re.search(r"\b(pull|pr)\b", utterance, re.I) else "issue"
        return {"kind": kind, "number": number}
    if name == "explain_fix":
        return {"query": utterance}
    if name == "open_repository":
        return {"repo": _named_repo(utterance)}
    if name == "set_map_layer":
        layer = "heat"
        if re.search(r"\b(import|edge)", utterance, re.I):
            layer = "edges"
        elif re.search(r"\b(line|loc|size)\b", utterance, re.I):
            layer = "loc"
        enabled = not bool(re.search(r"\b(off|hide|disable)\b", utterance, re.I))
        return {"layer": layer, "enabled": enabled}
    if name in {"list_recent_commits", "scrub_history", "list_open_issues", "list_pull_requests"}:
        match = re.search(r"\b(\d+)\b", utterance)
        count = int(match.group(1)) if match else (5 if name == "list_recent_commits" else 10)
        return {"count": count}
    if name == "confirm_write":
        return {"confirmed": bool(re.search(r"\b(yes|yeah|confirm|do it|go ahead)\b", utterance, re.I))}
    if name == "create_issue":
        title, body = _parse_issue_title_body(utterance)
        return {"title": title, "body": body}
    if name == "add_comment":
        parsed = _parse_comment_request(utterance)
        if parsed:
            return parsed[1]
        return {}
    if name == "review_changes":
        match = re.search(r"\b(\d+)\b", utterance)
        return {"pr_number": int(match.group(1))} if match and re.search(r"\b(pull|pr)\b", utterance, re.I) else {}
    return {}


def _wants_issue_comment(text: str) -> bool:
    raw = text or ""
    if not re.search(r"\b(issues?|pull|pr)\b", raw, re.I):
        return False
    return bool(
        re.search(r"\b(reply|respond|comment|write back)\b", raw, re.I)
        or re.search(r"\bcomment\s+on\b", raw, re.I)
        or re.search(r"\bleave\s+a\s+comment\b", raw, re.I)
        or re.search(r"\bpost\s+(?:a\s+)?comment\b", raw, re.I)
    )


def _comment_body(text: str) -> str:
    raw = text or ""
    patterns = [
        r"\b(?:reply|respond)\s+with\s+(?:a\s+)?(.+)$",
        r"\band\s+reply\s+with\s+(?:a\s+)?(.+)$",
        r"\bwith\s+(?:a\s+)?(.+)$",
        r"\b(?:saying|that says)\s+(.+)$",
        r"\bcomment\s+(?:on\s+.+?\s+)?(?:that|saying)\s+(.+)$",
    ]
    for pattern in patterns:
        hit = re.search(pattern, raw, re.I)
        if hit:
            body = hit.group(1).strip().rstrip(".")
            body = re.sub(r"^(?:on\s+the\s+issue|to\s+the\s+issue)\b", "", body, flags=re.I).strip()
            if body:
                return body
    return ""


def _issue_number_from_text(text: str) -> int:
    raw = text or ""
    for pattern in (
        r"\bissue\s+number\s+is\s+#?(\d+)\b",
        r"\bissue\s+(?:number\s+is\s+)?#?(\d+)\b",
        r"\bissues?\s+#(\d+)\b",
        r"\b(?:number|#)\s*(\d+)\b",
        r"\bissue\s+(\d+)\b",
    ):
        hit = re.search(pattern, raw, re.I)
        if hit:
            return int(hit.group(1))
    if re.search(r"\b(just created|you created|last issue|that issue|you just)\b", raw, re.I):
        return github_tools.last_posted_issue()
    return 0


def _issue_title_ref(text: str) -> str:
    raw = text or ""
    quoted = re.search(
        r"\bissue\s+(?:called|named|titled)\s+[\"“'](.+?)[\"”']",
        raw,
        re.I,
    )
    if quoted:
        return quoted.group(1).strip()
    plain = re.search(
        r"\bissue\s+(?:called|named|titled)\s+(.+?)\s+with\s+",
        raw,
        re.I,
    )
    if plain:
        return plain.group(1).strip(" .")
    return ""


def _parse_comment_request(text: str) -> tuple | None:
    if not _wants_issue_comment(text):
        return None
    number = _issue_number_from_text(text)
    title_ref = _issue_title_ref(text)
    if not number and title_ref:
        number = github_tools.find_issue_number(title_ref)
    body = _comment_body(text)
    if not number:
        return ("need_issue_number", {})
    if not body:
        _set_pending_comment(int(number))
        return ("need_comment_body", {"issue_number": int(number)})
    return ("add_comment", {"issue_number": int(number), "body": body})


def _comment_followup(text: str) -> tuple | None:
    """Next short utterance after we asked what to say on an issue."""
    if not _PENDING_COMMENT_ON:
        return None
    raw = (text or "").strip()
    if not raw or _bare_answer(raw):
        return None
    if _wants_new_issue(raw) or _wants_issue_comment(raw):
        return None
    if len(raw) > 500:
        return None
    return ("add_comment", {"issue_number": _PENDING_COMMENT_ON, "body": raw})


def _normalize_add_comment(name: str, args: dict, utterance: str) -> tuple[str, dict]:
    if name != "add_comment":
        return name, args
    parsed = _parse_comment_request(utterance)
    if parsed:
        return parsed[0], parsed[1]
    args = dict(args or {})
    number = int(args.get("issue_number") or 0)
    body = (args.get("body") or "").strip()
    if number and body:
        return name, {"issue_number": number, "body": body}
    if number and not body:
        _set_pending_comment(number)
        return "need_comment_body", {"issue_number": number}
    return "need_issue_number", {}


def _wants_new_issue(text: str) -> bool:
    raw = text or ""
    if _wants_issue_comment(raw):
        return False
    if re.search(r"\b(titled|named|called)\b", raw, re.I) and re.search(r"\bissues?\b", raw, re.I):
        return bool(re.search(r"\b(open|create|file|draft|make|write|start|want)\b", raw, re.I))
    return bool(re.search(r"\b(open|create|file|draft|make|write|start)\s+an\s+issues?\b", raw, re.I))


def _parse_issue_title_body(text: str) -> tuple:
    raw = text or ""
    title = ""
    body = ""
    quoted = re.search(r"(?:titled|named|called|title)\s+[\"“'](.+?)[\"”']", raw, re.I)
    if quoted:
        title = quoted.group(1).strip()
    else:
        plain = re.search(
            r"(?:titled|named|called)\s+(.+?)(?:\s+(?:for me|please|now|thanks)\b|\s+that says\b|\s+says\b|$)",
            raw,
            re.I,
        )
        if plain:
            title = plain.group(1).strip(" .")
        title_is = re.search(
            r"\btitle\s+is\s+(.+?)(?:\s+and\s+(?:the\s+)?body\b|\s*[.!]|$)",
            raw,
            re.I,
        )
        if title_is:
            title = title_is.group(1).strip(" .")
        call_it = re.search(r"\b(?:call|name)\s+it\s+(.+?)(?:\s+and\s+(?:the\s+)?body\b|\s*[.!]|$)", raw, re.I)
        if call_it:
            title = call_it.group(1).strip(" .")
    for pattern in (
        r"\b(?:that says|says)\s+(.+)$",
        r"\bbody\s+(?:should be|is)\s+(.+)$",
        r"\band\s+(?:the\s+)?body\s+(?:should be|is)\s+(.+)$",
    ):
        hit = re.search(pattern, raw, re.I)
        if hit:
            body = hit.group(1).strip().rstrip(".")
            break
    if title and re.search(r"\band\s+(?:the\s+)?body\b", title, re.I):
        title = re.split(r"\band\s+(?:the\s+)?body\b", title, maxsplit=1, flags=re.I)[0].strip(" .")
    return title, body


def _issue_draft(text: str) -> tuple:
    return _parse_issue_title_body(text)


def _issue_followup(text: str) -> tuple | None:
    """After need_issue_title, the next short reply is the title (Jev often picks create_issue)."""
    if _PENDING_ISSUE_AWAITING != "title":
        return None
    raw = (text or "").strip()
    if not raw or _bare_answer(raw):
        return None
    if _wants_issue_comment(raw) or (_wants_new_issue(raw) and _parse_issue_title_body(raw)[0]):
        return None
    title, body = _parse_issue_title_body(raw)
    if not title and len(raw.split()) <= 14 and not re.search(r"\b(landmark|map|commit|focus)\b", raw, re.I):
        title = raw.strip(" .")
    if not title:
        return ("need_issue_title", {})
    _clear_pending_issue()
    return ("create_issue", {"title": title, "body": body})


def _normalize_create_issue(name: str, args: dict, utterance: str) -> tuple[str, dict]:
    if name != "create_issue":
        return name, args
    follow = _issue_followup(utterance)
    if follow:
        return follow[0], follow[1]
    parsed_title, parsed_body = _parse_issue_title_body(utterance)
    args = dict(args or {})
    title = (args.get("title") or parsed_title or "").strip()
    body = (args.get("body") or parsed_body or "").strip()
    if title:
        _clear_pending_issue()
        return "create_issue", {"title": title, "body": body}
    if _PENDING_ISSUE_AWAITING == "title":
        return "need_issue_title", {}
    return "need_issue_title", {}


def _bare_answer(text: str) -> str:
    match = re.fullmatch(r"\s*(yes|yeah|yep|yup|no|nope|cancel)[.!]?\s*", text or "", re.I)
    return (match.group(1) if match else "").lower()


def _wants_landmark_explanation(text: str) -> bool:
    """Explain the landmark files. A bare 'what are the landmarks' still only lists them."""
    raw = text or ""
    if not re.search(r"\blandmarks?\b", raw, re.I):
        return False
    if re.search(r"\b(each|every|those|these)\b", raw, re.I) and re.search(
        r"\b(explain|what|tell|describe|do|does|about|mean)\b", raw, re.I
    ):
        return True
    return bool(re.search(r"\b(explain|describe)\b(?:\s+\w+){0,4}\s+landmarks?\b", raw, re.I))


def _direct(utterance: str, payload: dict) -> tuple:
    """Return a tool for a request that has only one sensible action."""
    text = utterance or ""
    files = payload.get("files") or {}
    bare = _bare_answer(text)
    if bare:
        confirmed = bare in {"yes", "yeah", "yep", "yup"}
        return "confirm_write", {"confirmed": confirmed}
    follow = _comment_followup(text)
    if follow:
        return follow
    issue_follow = _issue_followup(text)
    if issue_follow:
        return issue_follow
    comment = _parse_comment_request(text)
    if comment:
        return comment
    if _wants_new_issue(text):
        title, body = _issue_draft(text)
        if not title:
            return "need_issue_title", {}
        return "create_issue", {"title": title, "body": body}
    if re.search(r"\b(close|delete)\b", text, re.I) and re.search(r"\b(issues?|pull|pr)\b", text, re.I):
        return "refuse_close", {}
    if re.search(r"\b(map|circles?)\b", text, re.I) and re.search(r"\b(explain|describe|what|tell)\b", text, re.I):
        return "describe_map", {}
    if (
        re.search(r"\b(repository|repo)\b", text, re.I)
        and re.search(r"\b(open|owner|owns|belong)\b", text, re.I)
        and not re.search(r"\b(issues?|commits?|pull|prs?|security|scan|spam)\b", text, re.I)
    ):
        return "name_open_repo", {}
    if _wants_landmark_explanation(text):
        return "explain_landmarks", {}
    if re.search(r"\blandmarks?\b", text, re.I) or re.search(r"\blandmark\s+files?\b", text, re.I):
        return "list_landmarks", {}
    if re.search(r"\b(import|edges?)\b", text, re.I) and re.search(r"\b(show|hide|link|links|turn|display)\b", text, re.I):
        enabled = not bool(re.search(r"\b(hide|off|disable)\b", text, re.I))
        return "set_map_layer", {"layer": "edges", "enabled": enabled}
    if re.search(r"\b(circles?|size)\b", text, re.I) and re.search(r"\b(lines?|loc)\b", text, re.I):
        return "set_map_layer", {"layer": "loc", "enabled": True}
    if re.search(r"\bheat\b", text, re.I) and re.search(r"\b(hide|off|disable|show|turn)\b", text, re.I):
        enabled = not bool(re.search(r"\b(hide|off|disable)\b", text, re.I))
        return "set_map_layer", {"layer": "heat", "enabled": enabled}
    if re.search(r"\b(largest|biggest)\b", text, re.I) and re.search(r"\bfiles?\b", text, re.I) and files:
        path = max(files, key=lambda item: ((files[item] or {}).get("loc") or 0, item))
        if re.search(r"\b(do|does|explain|purpose|work)\b", text, re.I):
            return "explain_file", {"path": path}
        return "focus_file", {"path": path}
    if re.search(r"\b(entry|start|starts|main)\b", text, re.I) and re.search(r"\b(focus|where|program|begin|file)\b", text, re.I):
        entries = [item["path"] for item in (payload.get("landmarks") or []) if item.get("entry")]
        if not entries:
            return "no_entry", {}
        return "focus_file", {"path": entries[0]}
    if re.search(r"\b(who|author)\b", text, re.I) and re.search(r"\b(wrote|touched|author|committed)\b", text, re.I):
        return "who_touched", {"path": _named_path(text, files) or _FOCUS or ""}
    if re.search(r"\b(architecture|pieces)\b", text, re.I) or re.search(r"\bfit together\b", text, re.I):
        return "explain_architecture", {}
    if re.search(r"\b(review|safe|merge)\b", text, re.I) and re.search(r"\bcommits?\b", text, re.I):
        return "review_changes", {}
    if re.search(r"\b(changed|change|diff)\b", text, re.I) and re.search(r"\b(latest|last|recent)\b", text, re.I) and re.search(r"\bcommits?\b", text, re.I):
        return "latest_change", {}
    if re.search(r"\bcommits?\b", text, re.I):
        match = re.search(r"\b(\d+)\b", text)
        count = int(match.group(1)) if match else 5
        return "list_recent_commits", {"count": count}
    if re.search(r"\b(spam|repeated|noise)\b", text, re.I):
        return "scan_noise", {}
    if re.search(r"\b(security|secret|vulnerab)\b", text, re.I):
        return "scan_security", {}
    if re.search(r"\b(read|show)\b", text, re.I) and re.search(r"\b(issues?|pull|pr)\b", text, re.I):
        match = re.search(r"#(\d+)|\b(\d+)\b", text)
        number = int(next(group for group in match.groups() if group)) if match else 0
        kind = "pull" if re.search(r"\b(pull|pr)\b", text, re.I) else "issue"
        return "read_thread", {"kind": kind, "number": number}
    if re.search(r"\bissues?\b", text, re.I) and re.search(r"\b(open|any|there)\b", text, re.I):
        return "list_open_issues", {}
    if re.search(r"\b(pull requests?|prs?)\b", text, re.I):
        return "list_pull_requests", {}
    return None


def _local_say(name: str, payload: dict, slug: str, args: dict | None = None) -> str:
    if name == "name_open_repo":
        owner = payload.get("owner") or (slug.split("/")[0] if "/" in slug else slug)
        repo = payload.get("repo") or (slug.split("/")[-1] if "/" in slug else slug)
        home = f"https://github.com/{slug}" if slug else ""
        sentence = f"{repo} is open. {owner} owns it."
        return f"{sentence} [{slug}]({home})." if home else sentence
    if name == "no_entry":
        return "No file on this map is marked as an entry point."
    if name == "refuse_close":
        return "I don't close issues or pull requests."
    if name == "need_issue_title":
        return "What should the issue be titled?"
    if name == "need_issue_number":
        return "Which issue number should I comment on? You can also say the issue title."
    if name == "need_comment_body":
        number = int((args or {}).get("issue_number") or _PENDING_COMMENT_ON or 0)
        return f"What should I say on issue {number}?" if number else "What should the comment say?"
    return ""


def _github_gateway_mode() -> str:
    """off | fallback | multi | all — multi is the default (Gateway triage only)."""
    raw = (os.environ.get("FRIDAY_GITHUB_GATEWAY") or "multi").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return "off"
    if raw in {"fallback", "multi", "all"}:
        return raw
    return "multi"


def _use_github_gateway() -> bool:
    if _github_gateway_mode() == "off":
        return False
    provider = (os.environ.get("AGENT_LLM_PROVIDER") or "assemblyai").strip().lower()
    return provider == "assemblyai"


def _needs_map_orchestrator(utterance: str) -> bool:
    raw = utterance or ""
    patterns = (
        r"\blandmarks?\b",
        r"\b(map|circles?)\b",
        r"\bfocus\b",
        r"\bheat\s+layer\b",
        r"\bimport\s+links?\b",
        r"\bentry\s+(file|point)\b",
        r"\bwho\s+(wrote|touched)\b",
        r"\barchitecture\b",
        r"\bscan\b.*\b(security|repository|repo)\b",
        r"\bspam\b",
        r"\bscrub\b",
        r"\bexplain\s+(each|every)\b.*\blandmarks?\b",
        r"\blargest\s+file\b",
        r"\bwhere\s+does\b.*\bstart\b",
        r"\bexplain\s+.*\bfile\b",
        r"\bwhat\s+does\s+.*\bfile\b",
    )
    return any(re.search(pattern, raw, re.I) for pattern in patterns)


def _wants_github_gateway(utterance: str) -> bool:
    """When to use the Gateway agent loop instead of one Jev tool."""
    raw = utterance or ""
    if _needs_map_orchestrator(raw):
        return False
    mode = _github_gateway_mode()
    if mode == "all":
        return bool(re.search(r"\b(issue|commit|pull|pr|comment|diff|merge|tracker)\b", raw, re.I))
    if mode == "fallback":
        return False
    # multi: spoken commit/issue triage via run_agent.
    if re.search(r"\b(check|review|inspect|look at|read)\b", raw, re.I) and re.search(
        r"\b(commit|commits|diff|change|changes)\b", raw, re.I
    ):
        return True
    if re.search(r"\b(latest|last|recent)\b", raw, re.I) and re.search(r"\bcommit", raw, re.I):
        return True
    if re.search(r"\bif\b", raw, re.I) and re.search(r"\b(broken|issue|fix|bug)\b", raw, re.I):
        return True
    if re.search(r"\b(tell me|what)\b", raw, re.I) and re.search(r"\b(changed|change)\b", raw, re.I):
        return True
    return False


def _gateway_turn(utterance: str, turn_id: str) -> dict:
    from agent import run_agent

    found = run_agent(utterance, transcript_id=turn_id)
    say = (found.get("summary") or "").strip() or GIVE_UP
    steps = [{"step": "gateway", "detail": "run_agent"}]
    for call in found.get("tool_calls") or []:
        steps.append({"step": "tool", "detail": call.get("name") or "tool"})
    _remember(utterance, say)
    return {
        "say": say,
        "spoken": say,
        "paths": [],
        "steps": steps,
        "ui_commands": [],
    }


def _strip_reload(commands: list, slug: str) -> list:
    kept = []
    for command in commands or []:
        if command.get("type") == "load_map" and command.get("repo") == slug:
            continue
        kept.append(command)
    return kept


def turn(utterance: str) -> dict:
    """Answer one utterance with one tool."""
    utterance = (utterance or "").strip()
    if not utterance:
        raise RuntimeError("Say something first.")
    payload = map_pipeline.get_cached(github_tools.active_repo())
    if not payload:
        raise RuntimeError("No repository is open.")
    slug = payload.get("slug") or github_tools.active_repo()
    turn_id = uuid.uuid4().hex
    direct = _direct(utterance, payload)
    if not direct and _use_github_gateway() and _wants_github_gateway(utterance):
        return _gateway_turn(utterance, turn_id)
    if direct:
        name, args = direct
        decided_by = "command"
        confidence = None
    else:
        try:
            decision = jev_gate.choose_tool(_state(payload, utterance))
        except Exception:
            decision = {"answers": {}}
        name, confidence = jev_gate.tool_choice(decision)
        decided_by = "jev"
        allowed = set(jev_gate.TOOL_CRITERIA)
        if not (isinstance(confidence, (int, float)) and confidence >= jev_gate.ACCEPT_AT and name in allowed):
            picked = specialists.k2_choose_tool(_state(payload, utterance), list(jev_gate.TOOL_CRITERIA))
            name = picked.get("tool") or "give_up"
            decided_by = "k2"
            confidence = None
        if _asks_about_project(utterance):
            name = "explain_project"
        elif _asks_what_it_does(utterance) and name in {"focus_file", "open_repository", "describe_map", "give_up"}:
            name = "explain_file"
        if name == "open_repository" and _named_repo(utterance) in {"", slug}:
            name = "describe_map"
        args = {} if name in {"give_up", "explain_project"} else _arguments(name, utterance, payload)
        if name == "explain_file" and not (args.get("path") or _FOCUS):
            name = "explain_project"
            args = {}
    name, args = _normalize_create_issue(name, args, utterance)
    name, args = _normalize_add_comment(name, args, utterance)
    import orchestrator

    local = _local_say(name, payload, slug, args)
    if local:
        if name == "need_issue_title":
            _set_pending_issue_title()
        _remember(utterance, local)
        return {
            "say": local,
            "spoken": local,
            "paths": [],
            "steps": [{"step": decided_by, "detail": name, "confidence": confidence}],
            "ui_commands": [],
        }
    found = orchestrator.dispatch(name, args, utterance, turn_id)
    if (
        found.get("is_error")
        and _use_github_gateway()
        and _github_gateway_mode() in {"fallback", "multi", "all"}
        and name in {"add_comment", "create_issue"}
    ):
        return _gateway_turn(utterance, turn_id)
    if name == "create_issue" and not found.get("is_error"):
        _clear_pending_issue()
    if name == "add_comment" and not found.get("is_error"):
        _set_pending_comment(0)
    say = found.get("say") or GIVE_UP
    commands = _strip_reload(found.get("ui_commands") or [], slug)
    for command in commands:
        if command.get("type") == "focus" and command.get("path"):
            note_focus(command["path"])
    steps = [{"step": decided_by, "detail": name, "confidence": confidence}]
    steps.extend(found.get("trace") or [])
    result = found.get("result") or {}
    paths = list(result.get("paths") or [])
    if args.get("path"):
        paths = [args["path"]]
    spoken = result.get("spoken") or say
    _remember(utterance, say)
    return {"say": say, "spoken": spoken, "paths": paths, "steps": steps, "ui_commands": commands}
