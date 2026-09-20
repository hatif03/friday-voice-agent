"""Answer a question from files already on the map.

Name overlap picks the files. A short gateway call writes the answer.
Paths that are not in the map are dropped.
"""
import os
import re

from openai import OpenAI

from github_tools import active_repo
import map_pipeline

_STOP = {
    "the", "and", "for", "with", "this", "that", "what", "when", "where", "which",
    "who", "why", "how", "does", "did", "can", "should", "about", "from", "into",
    "file", "files", "repo", "repository", "please", "show", "tell",
}
_ASK_SYSTEM = (
    "You answer a question about one open repository. "
    "Reply with JSON only, no markdown fence: "
    '{"summary":"two or three spoken sentences","safe":false,"paths":["real/file.py"],"concerns":[]}. '
    "paths must be copied from the FILE headers in the evidence. Do not invent a path. "
    "If the excerpts do not contain the answer, say so in summary."
)


def answer(question: str) -> dict:
    question = (question or "").strip()
    if not question:
        raise RuntimeError("Type a question first.")
    payload = map_pipeline.get_cached(active_repo())
    if not payload:
        raise RuntimeError("No repository is open.")
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
    draft = _complete(evidence)
    known = set(payload["files"])
    paths = [path for path in (draft.get("paths") or []) if path in known]
    if not paths:
        paths = [path for path in chosen if path in known][:6]
    say = draft.get("summary") or _grounded(question, paths, texts)
    if draft.get("error") and not draft.get("summary"):
        say = _grounded(question, paths, texts)
    steps = [
        {"step": "heard", "detail": question[:400]},
        {"step": "files", "detail": ", ".join(paths[:8]) or "none"},
        {"step": "gateway", "detail": say[:400]},
    ]
    if draft.get("error"):
        steps.append({"step": "gateway", "detail": str(draft["error"])[:240]})
    try:
        import store

        store.record_query(payload["slug"], question, say, steps)
    except Exception:
        pass
    return {"say": say, "paths": paths, "steps": steps}


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


def _complete(evidence: str) -> dict:
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return {"summary": "The language gateway key is not set.", "paths": [], "error": "missing key"}
    client = OpenAI(base_url="https://llm-gateway.assemblyai.com/v1", api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="qwen3.5-4b-32k-fast",
            messages=[
                {"role": "system", "content": _ASK_SYSTEM},
                {"role": "user", "content": evidence[:12000]},
            ],
            max_tokens=500,
            temperature=0.2,
        )
    except Exception as exc:
        return {"summary": "", "paths": [], "error": str(exc)[:240]}
    from specialists import _parse_reader

    return _parse_reader(response.choices[0].message.content or "", "llm_gateway")
