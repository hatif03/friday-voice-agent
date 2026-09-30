"""Answer a question about the open repository.

The gateway can call the same tools as the voice agent. File excerpts are
used only when it does not call a tool. Paths that are not on the map are dropped.
"""
import json
import os
import re

from openai import OpenAI

import github_tools
import map_pipeline
from voice_broker import VOICE_TOOLS

_STOP = {
    "the", "and", "for", "with", "this", "that", "what", "when", "where", "which",
    "who", "why", "how", "does", "did", "can", "should", "about", "from", "into",
    "file", "files", "repo", "repository", "please", "show", "tell",
}
_TOOL_SYSTEM = (
    "Decide whether this request needs a Friday tool. "
    "Call focus_file when they ask to focus, show, open, or zoom to a file. "
    "If they say the main entry and do not name a path, call focus_file with the first entry path listed. "
    "Call list_landmarks for landmarks, entry points, core files, or hotspots. "
    "Call describe_map when they ask about the map. "
    "Call set_map_layer for heat, imports, or line size. "
    "Call a tool for issues, pull requests, commits, authors, a thread, a review, "
    "architecture, security, or noise. "
    "If they ask how the source works and no tool fits, reply with the single word CODE."
)
_FILE_SYSTEM = (
    "You answer from the file excerpts only. "
    "Reply with JSON only, no markdown fence: "
    '{"summary":"two or three spoken sentences","paths":["real/file.py"]}. '
    "paths must be copied from the FILE headers. Do not invent a path. "
    "If the excerpts do not contain the answer, set summary to "
    "'That is not in the files on the map.' and paths to []. Do not quote unrelated code."
)
_SKIP_TOOLS = {"ask_repository"}
_ASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
        },
    }
    for tool in VOICE_TOOLS
    if tool.get("name") not in _SKIP_TOOLS
]


def _about_the_map(question: str) -> bool:
    return bool(re.search(r"\b(map|fingerprint|circle|circles)\b", question, re.I)) and not _about_landmarks(question) and not _about_largest(question)


def _about_landmarks(question: str) -> bool:
    return bool(re.search(r"\blandmarks?\b", question, re.I))


def _about_largest(question: str) -> bool:
    return bool(re.search(r"\b(largest|biggest|longest)\b", question, re.I)) and bool(re.search(r"\bfiles?\b", question, re.I))


def _about_entry(question: str) -> bool:
    return bool(re.search(r"\b(focus|zoom|show|open)\b", question, re.I)) and bool(
        re.search(r"\b(entry|main)\b", question, re.I)
    )


def _flags(item: dict) -> str:
    names = [name for name in ("entry", "core", "hotspot") if item.get(name)]
    return ", ".join(names) or "file"


def _landmarks(payload: dict) -> dict:
    items = payload.get("landmarks") or []
    if not items:
        say = "No file on this map is marked as an entry point, a core file, or a hotspot."
        return {"say": say, "paths": [], "steps": [{"step": "landmarks", "detail": "none"}]}
    shown = items[:8]
    bits = [f"{item['path']} ({_flags(item)}, {item.get('loc', 0)} lines)" for item in shown]
    say = "Landmarks on this map: " + "; ".join(bits) + "."
    paths = [item["path"] for item in shown]
    return {
        "say": say,
        "paths": paths,
        "steps": [{"step": "landmarks", "detail": "; ".join(bits)}],
    }


def _largest(payload: dict, question: str) -> dict:
    files = payload.get("files") or {}
    if not files:
        return {"say": "This map has no files.", "paths": [], "steps": [{"step": "files", "detail": "none"}]}
    path = max(files, key=lambda item: (files[item].get("loc") or 0, item))
    meta = files[path]
    loc = meta.get("loc") or 0
    text = ((payload.get("source_text") or {}).get(path) or "").strip()
    excerpt = " ".join(text.split()[:60])
    proof = f"{path}, {loc} lines"
    say = f"The largest file is {proof}."
    if excerpt and re.search(r"\b(do|does|explain|purpose|work)\b", question, re.I):
        draft = _complete(
            f"QUESTION\n{question}\n\nFILE {path}\n{loc} lines\n{text[:2500]}\n\n"
            "Explain only this file. Two sentences. Do not mention files that are not in the excerpt."
        )
        summary = (draft.get("summary") or "").strip()
        if summary:
            say = f"The largest file is {proof}. {summary}"
    elif excerpt:
        say = f"The largest file is {proof}. It opens with: {excerpt}"
    return {
        "say": say,
        "paths": [path],
        "steps": [
            {"step": "files", "detail": proof},
            {"step": "excerpt", "detail": excerpt[:240] or "no source text in view"},
        ],
    }


def answer(question: str) -> dict:
    question = (question or "").strip()
    if not question:
        raise RuntimeError("Type a question first.")
    payload = map_pipeline.get_cached(github_tools.active_repo())
    if not payload:
        raise RuntimeError("No repository is open.")
    if _about_landmarks(question):
        result = _landmarks(payload)
        _remember(payload, question, result)
        return result
    if _about_largest(question):
        result = _largest(payload, question)
        _remember(payload, question, result)
        return result
    if _about_entry(question):
        result = _focus_entry(payload, question)
        _remember(payload, question, result)
        return result
    if _about_the_map(question):
        say = map_pipeline.explain_map(payload)
        paths = [item["path"] for item in (payload.get("landmarks") or [])[:8]]
        steps = [
            {"step": "map", "detail": payload.get("slug") or ""},
            {"step": "landmarks", "detail": ", ".join(paths) or "none"},
        ]
        result = {"say": say, "paths": paths, "steps": steps}
        _remember(payload, question, result)
        return result
    drafted = _gateway(
        [
            {"role": "system", "content": _TOOL_SYSTEM},
            {"role": "user", "content": _tool_brief(payload, question)},
        ],
        tools=_ASK_TOOLS,
    )
    if drafted.error:
        result = {
            "say": "I could not call a tool for that.",
            "paths": [],
            "steps": [{"step": "tool", "detail": drafted.error[:240]}],
        }
        _remember(payload, question, result)
        return result
    called = _run_called_tools(question, drafted.tool_calls)
    if called:
        _remember(payload, question, called)
        return called
    chosen = _pick(payload, question)
    texts = payload.get("source_text") or {}
    blocks = []
    for path in chosen:
        text = texts.get(path)
        if text:
            blocks.append(f"FILE {path}\n{text[:1200]}")
    stats = payload.get("stats") or {}
    evidence = (
        f"QUESTION\n{question}\n\n"
        f"STATS\nfiles={stats.get('files')} lines={stats.get('loc')} imports={stats.get('edges')}\n\n"
        + "\n\n".join(blocks)
    )
    from specialists import _parse_reader

    file_draft = _gateway(
        [
            {"role": "system", "content": _FILE_SYSTEM},
            {"role": "user", "content": evidence[:12000]},
        ]
    )
    draft = _parse_reader(file_draft.content or "", "llm_gateway")
    if file_draft.error:
        draft = {"summary": "", "paths": [], "error": file_draft.error}
    known = set(payload["files"])
    paths = [path for path in (draft.get("paths") or []) if path in known]
    say = (draft.get("summary") or "").strip() or "That is not in the files on the map."
    steps = [
        {"step": "heard", "detail": question[:400]},
        {"step": "files", "detail": ", ".join(paths[:8]) or "none"},
        {"step": "gateway", "detail": say[:400]},
    ]
    if draft.get("error"):
        steps.append({"step": "gateway", "detail": str(draft["error"])[:240]})
    result = {"say": say, "paths": paths, "steps": steps}
    _remember(payload, question, result)
    return result


def _remember(payload: dict, question: str, result: dict) -> None:
    try:
        import store

        store.record_query(payload["slug"], question, result.get("say") or "", result.get("steps") or [])
    except Exception:
        return


def _grounded(question: str, paths: list, texts: dict) -> str:
    if not paths:
        return "Nothing on the map matched that question."
    names = ", ".join(paths[:4])
    excerpt = ""
    for path in paths:
        text = (texts.get(path) or "").strip()
        if text:
            excerpt = " ".join(text.split()[:40])
            break
    if excerpt:
        return f"The closest files are {names}. {excerpt}"
    return f"The closest files are {names}. I do not have their text in this view."


def _pick(payload: dict, question: str) -> list:
    tokens = [token for token in re.findall(r"[a-z0-9_./-]{2,}", question.lower()) if token not in _STOP]
    scored = []
    for path, meta in payload["files"].items():
        hay = path.lower()
        score = sum(3 for token in tokens if token in hay)
        score += len(meta.get("imports") or []) + len(meta.get("imported_by") or [])
        if score:
            scored.append((score, path))
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen = [path for _score, path in scored[:8]]
    if chosen:
        return chosen
    return [item["path"] for item in (payload.get("landmarks") or [])[:6]]


def _focus_entry(payload: dict, question: str) -> dict:
    entries = [item["path"] for item in (payload.get("landmarks") or []) if item.get("entry")]
    if not entries:
        say = "No file on this map is marked as an entry point."
        return {"say": say, "paths": [], "steps": [{"step": "focus", "detail": "no entry"}], "ui_commands": []}
    import orchestrator

    found = orchestrator.dispatch("focus_file", {"path": entries[0]}, question, "ask")
    return {
        "say": found.get("say") or entries[0],
        "paths": [entries[0]],
        "steps": found.get("trace") or [{"step": "tool", "name": "focus_file"}],
        "ui_commands": found.get("ui_commands") or [{"type": "focus", "path": entries[0]}],
    }


def _tool_brief(payload: dict, question: str) -> str:
    lines = [f"Repository {payload.get('slug') or github_tools.active_repo()}", question]
    entries = [item["path"] for item in (payload.get("landmarks") or []) if item.get("entry")][:6]
    if entries:
        lines.append("Entry files: " + ", ".join(entries))
    return "\n".join(lines)


def _run_called_tools(question: str, tool_calls) -> dict | None:
    """Run the tools the model chose. Speak their say fields. No second model pass."""
    if not tool_calls:
        return None
    import orchestrator

    says = []
    steps = []
    commands = []
    for call in list(tool_calls)[:3]:
        name = call.function.name
        if name in _SKIP_TOOLS:
            continue
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        found = orchestrator.dispatch(name, args, question, "ask")
        steps.extend(found.get("trace") or [{"step": "tool", "name": name}])
        commands.extend(found.get("ui_commands") or [])
        if found.get("say"):
            says.append(found["say"])
    if not says:
        return None
    return {"say": " ".join(says), "paths": [], "steps": steps, "ui_commands": commands}


class _GatewayMessage:
    def __init__(self, content="", tool_calls=None, error=None):
        self.content = content or ""
        self.tool_calls = tool_calls
        self.error = error


def _k2(messages: list, max_tokens: int = 1200) -> _GatewayMessage:
    """Prose answers use K2 Horizon. Tool choice stays on the low-effort path."""
    api_key = os.environ.get("IFM_API_TOKEN") or os.environ.get("IFM_API_KEY")
    if not api_key:
        return _GatewayMessage(error="IFM_API_TOKEN is not set")
    client = OpenAI(base_url=os.environ.get("IFM_BASE_URL", "https://api.ifm.ai/v1"), api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=os.environ.get("IFM_MODEL", "IFM/K2-Horizon-375B-A23B"),
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
            extra_body={"reasoning_effort": "high"},
        )
    except Exception as exc:
        return _GatewayMessage(error=str(exc)[:240])
    message = response.choices[0].message
    return _GatewayMessage(content=message.content or "")


def _gateway(messages: list, tools=None, max_tokens: int = 500) -> _GatewayMessage:
    """File answers use the fast gateway model. Tool choice uses K2, which can call tools."""
    if tools:
        api_key = os.environ.get("IFM_API_TOKEN") or os.environ.get("IFM_API_KEY")
        if not api_key:
            return _GatewayMessage(error="IFM_API_TOKEN is not set, so no model that can call tools is available.")
        client = OpenAI(base_url=os.environ.get("IFM_BASE_URL", "https://api.ifm.ai/v1"), api_key=api_key)
        kwargs = {
            "model": os.environ.get("IFM_MODEL", "IFM/K2-Horizon-375B-A23B"),
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.2,
            "tools": tools,
            "tool_choice": "auto",
            "extra_body": {"reasoning_effort": "low"},
        }
    else:
        api_key = os.environ.get("ASSEMBLYAI_API_KEY")
        if not api_key:
            return _GatewayMessage(error="missing key")
        client = OpenAI(base_url="https://llm-gateway.assemblyai.com/v1", api_key=api_key)
        kwargs = {
            "model": "qwen3.5-4b-32k-fast",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        return _GatewayMessage(error=str(exc)[:240])
    message = response.choices[0].message
    return _GatewayMessage(content=message.content or "", tool_calls=getattr(message, "tool_calls", None))


_MANIFESTS = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "cargo.toml",
    "go.mod",
    "composer.json",
    "gemfile",
}


def select_files(question: str, payload: dict) -> list:
    """Pick the files a project question needs. README first for an overview."""
    files = payload.get("files") or {}
    mentioned = []
    for path in files:
        name = path.split("/")[-1]
        if not name:
            continue
        if re.search(r"(?<![\w.])" + re.escape(name) + r"(?![\w])", question or "", re.I):
            mentioned.append(path)
    overview = bool(re.search(r"\b(what|explain|overview|about|project|repo|repository|features|install|purpose)\b", question or "", re.I))
    picked = []

    def add(path: str) -> None:
        if path in files and path not in picked:
            picked.append(path)

    for path in mentioned:
        add(path)
    if overview or not mentioned:
        for path in files:
            base = path.split("/")[-1].lower()
            if base.startswith("readme") or base in _MANIFESTS:
                add(path)
        for item in payload.get("landmarks") or []:
            if item.get("entry") or item.get("core"):
                add(item.get("path") or "")
            if len(picked) >= 8:
                break
    return picked[:8]


def _folder_lines(paths: list) -> str:
    lines = []
    seen = set()
    for path in paths:
        parts = [part for part in path.split("/") if part]
        if len(parts) == 1:
            label = parts[0]
        else:
            label = parts[0] + "/"
        if label in seen:
            continue
        seen.add(label)
        lines.append("- " + label)
        if len(lines) >= 40:
            break
    return "\n".join(lines) or "- (no files)"


def _read_phrased(text: str) -> tuple:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            data = {}
        spoken = str(data.get("spoken") or "").strip()
        analysis = str(data.get("analysis") or "").strip()
        if spoken or analysis:
            return spoken, analysis
    return "", raw


def explain_repository(question: str, payload: dict, history=None) -> dict:
    """Answer from README and a few real files, the way a repository chat does."""
    paths = select_files(question, payload)
    texts = payload.get("source_text") or {}
    parts = [
        f"Repository: {payload.get('slug')}",
        "--- REPOSITORY FOLDER STRUCTURE ---",
        _folder_lines(list((payload.get("files") or {}).keys())),
        "--- SELECTED FILES ---",
        "\n".join(f"- {path}" for path in paths) or "- (none)",
    ]
    budget = 0
    used = []
    for path in paths:
        body = (texts.get(path) or "").strip()
        if not body:
            continue
        chunk = f"\n--- FILE: {path} ---\n{body[:6000]}\n"
        if budget + len(chunk) > 14000:
            break
        parts.append(chunk)
        budget += len(chunk)
        used.append(path)
    if not used:
        say = "I can't find an explanation of this project in the files on this map."
        return {"say": say, "spoken": say, "paths": []}
    recent = []
    for turn in (history or [])[-4:]:
        recent.append(f"User: {turn.get('user') or ''}")
        recent.append(f"Friday: {(turn.get('say') or '')[:240]}")
    system = (
        "You answer questions about one GitHub repository from the files in the evidence. "
        "Reply with JSON only: {\"spoken\":\"one or two sentences\",\"analysis\":\"markdown\"}. "
        "analysis starts with a heading Analysis, then short bullets. "
        "Bold the purpose and the file names you used. "
        "State only what those files say. "
        "If the files do not contain the answer, both fields are exactly: "
        "I cannot find the answer to this in the selected files."
    )
    user = "\n".join(parts)
    if recent:
        user += "\n--- RECENT TURNS ---\n" + "\n".join(recent)
    user += f"\n--- QUESTION ---\n{question}"
    drafted = _k2(
        [{"role": "system", "content": system}, {"role": "user", "content": user[:16000]}],
        max_tokens=1200,
    )
    if drafted.error or not (drafted.content or "").strip():
        say = "I can't find an explanation of this project in the files on this map."
        return {"say": say, "spoken": say, "paths": used}
    spoken, analysis = _read_phrased(drafted.content)
    say = analysis or spoken
    if not say:
        say = "I can't find an explanation of this project in the files on this map."
    if not spoken:
        spoken = re.sub(r"[#*`]", "", say)
        spoken = re.sub(r"\s+", " ", spoken).strip()[:320]
    return {"say": say, "spoken": spoken, "paths": used}


def _blurb(text: str) -> str:
    """A comment from the file when the model does not answer. Never a line of code."""
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw.startswith(("//", "#", "/*", "*")):
            continue
        cleaned = re.sub(r"^[#/*\s]+", "", raw).strip()
        if len(cleaned) >= 12 and not cleaned.startswith(("eslint", "ts-")):
            return cleaned[:180]
    return ""


def explain_landmarks(payload: dict) -> list:
    """One sentence per landmark, taken from that file's source."""
    items = (payload.get("landmarks") or [])[:12]
    texts = payload.get("source_text") or {}
    if not items:
        return []
    blocks = []
    for item in items:
        path = item.get("path") or ""
        excerpt = (texts.get(path) or "").strip()[:900]
        blocks.append(f"FILE {path}\n{excerpt or '(no source text on this map)'}")
    drafted = _k2(
        [
            {
                "role": "system",
                "content": (
                    "Explain these source files to a developer who has the repository open. "
                    "For each file, one or two plain sentences: what it is responsible for, and how it fits the rest. "
                    "No code, no identifier lists, no quotes from the source. "
                    'Reply with JSON only: {"files":[{"path":"the exact FILE path","sentence":"one or two sentences"}]}. '
                    "Include every FILE. Do not invent paths or behavior that is not in the excerpt."
                ),
            },
            {"role": "user", "content": "\n\n".join(blocks)[:14000]},
        ],
        max_tokens=1600,
    )
    allowed = {item.get("path") or "" for item in items}
    parsed = []
    raw = (drafted.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        data = None
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                data = None
    if isinstance(data, dict):
        for row in data.get("files") or []:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            sentence = str(row.get("sentence") or "").strip()
            if path in allowed and sentence:
                parsed.append({"path": path, "sentence": sentence})
    by_path = {row["path"]: row["sentence"] for row in parsed}
    found = []
    for item in items:
        path = item.get("path") or ""
        sentence = by_path.get(path) or _blurb(texts.get(path) or "")
        if not sentence:
            sentence = "I can't find an explanation of this file in the source on this map."
        found.append({"path": path, "sentence": sentence})
    return found


def explain_source(path: str, text: str) -> str:
    """Two sentences from this file only. Empty when the model cannot phrase it."""
    draft = _complete(
        f"FILE {path}\n{(text or '')[:2500]}\n\n"
        "What does this file do? Two sentences. Do not mention files that are not in the excerpt."
    )
    return (draft.get("summary") or "").strip()


def _complete(evidence: str) -> dict:
    drafted = _k2(
        [
            {"role": "system", "content": "Explain only the file in the evidence. Two sentences. No code."},
            {"role": "user", "content": evidence[:12000]},
        ],
        max_tokens=600,
    )
    if drafted.error:
        return {"summary": "", "paths": [], "error": drafted.error}
    from specialists import _parse_reader

    return _parse_reader(drafted.content, "llm_gateway")
