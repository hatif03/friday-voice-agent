"""Phrasing and escalated reads.

AssemblyAI phrases a decision code already accepted. Vertex Gemini decides
only when Jev is unsure. K2 is the backup if Gemini returns an error.
"""
import json
import os
import shutil
import subprocess

import requests
from openai import OpenAI

PHRASE_SYSTEM = (
    "You phrase a decision that code already made. "
    "Reply with JSON only, no markdown fence: "
    '{"summary":"two or three spoken sentences","paths":["real/file.py"],"concerns":["short point"]}. '
    "Do not decide whether the change is safe and do not add a safe field. "
    "Speak the decision written in the evidence. paths must be copied from the evidence, never invented."
)
PHRASE_MODEL = "qwen3.5-4b-32k-fast"

READER_SYSTEM = (
    "You review code for a human who cannot read every line. "
    "Reply with JSON only, no markdown fence: "
    '{"summary":"two or three spoken sentences","safe":false,"paths":["real/file.py"],"concerns":["short point"]}. '
    "safe is true only when you would merge this. paths must be copied from the evidence, never invented. "
    "Do not claim the change is safe if you are unsure."
)


def _parse_reader(text: str, source: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                data = None
        else:
            data = None
    if not isinstance(data, dict):
        return {"source": source, "error": "unreadable response", "summary": raw[:500], "safe": False, "paths": []}
    return {
        "source": source,
        "summary": str(data.get("summary") or "")[:1200],
        "safe": bool(data.get("safe")),
        "paths": [str(path) for path in (data.get("paths") or [])][:12],
        "concerns": [str(item) for item in (data.get("concerns") or [])][:8],
    }


def gateway_phrase(evidence: str) -> dict:
    """Speak the decision. This reply is not allowed to set safe."""
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return {"source": "llm_gateway", "error": "ASSEMBLYAI_API_KEY is not set", "summary": "", "paths": []}
    client = OpenAI(base_url="https://llm-gateway.assemblyai.com/v1", api_key=api_key)
    response = client.chat.completions.create(
        model=PHRASE_MODEL,
        messages=[
            {"role": "system", "content": PHRASE_SYSTEM},
            {"role": "user", "content": evidence[:24000]},
        ],
        max_tokens=900,
        temperature=0.2,
    )
    parsed = _parse_reader(response.choices[0].message.content or "", "llm_gateway")
    parsed.pop("safe", None)
    return parsed


def gateway_draft(evidence: str) -> dict:
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return {"source": "llm_gateway", "error": "ASSEMBLYAI_API_KEY is not set", "safe": False, "paths": []}
    client = OpenAI(base_url="https://llm-gateway.assemblyai.com/v1", api_key=api_key)
    response = client.chat.completions.create(
        model="qwen3-next-80b-a3b",
        messages=[
            {"role": "system", "content": READER_SYSTEM},
            {"role": "user", "content": evidence[:24000]},
        ],
        max_tokens=900,
        temperature=0.2,
    )
    return _parse_reader(response.choices[0].message.content or "", "llm_gateway")


def k2_choose_tool(evidence: str, names: list) -> dict:
    """Escalate a tool choice only when Jev is under 0.9. Low effort, one name."""
    api_key = os.environ.get("IFM_API_TOKEN") or os.environ.get("IFM_API_KEY")
    if not api_key:
        return {"source": "k2", "error": "IFM_API_TOKEN is not set", "tool": "give_up"}
    client = OpenAI(base_url=os.environ.get("IFM_BASE_URL", "https://api.ifm.ai/v1"), api_key=api_key)
    allowed = ", ".join(names)
    try:
        response = client.chat.completions.create(
            model=os.environ.get("IFM_MODEL", "IFM/K2-Horizon-375B-A23B"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Pick one tool. Reply with JSON only: {\"tool\":\"name\"}. "
                        f"tool must be one of: {allowed}. "
                        "explain_file answers what code does. focus_file only moves the map. "
                        "give_up when none of the tools can answer."
                    ),
                },
                {"role": "user", "content": evidence[:8000]},
            ],
            max_tokens=200,
            temperature=0.2,
            extra_body={"reasoning_effort": "low"},
        )
    except Exception as exc:
        return {"source": "k2", "error": str(exc)[:240], "tool": "give_up"}
    raw = (response.choices[0].message.content or "").strip()
    tool = ""
    try:
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        tool = str((data or {}).get("tool") or "")
    except (json.JSONDecodeError, ValueError):
        for name in names:
            if name in raw:
                tool = name
                break
    if tool not in names:
        tool = "give_up"
    return {"source": "k2", "tool": tool}


def k2_read(evidence: str) -> dict:
    api_key = os.environ.get("IFM_API_TOKEN") or os.environ.get("IFM_API_KEY")
    if not api_key:
        return {"source": "k2", "error": "IFM_API_TOKEN is not set", "safe": False, "paths": []}
    client = OpenAI(base_url=os.environ.get("IFM_BASE_URL", "https://api.ifm.ai/v1"), api_key=api_key)
    response = client.chat.completions.create(
        model=os.environ.get("IFM_MODEL", "IFM/K2-Horizon-375B-A23B"),
        messages=[
            {"role": "system", "content": READER_SYSTEM},
            {"role": "user", "content": evidence[:24000]},
        ],
        max_tokens=900,
        temperature=min(float(os.environ.get("IFM_TEMPERATURE", "0.3")), 0.3),
        extra_body={"reasoning_effort": "high"},
    )
    return _parse_reader(response.choices[0].message.content or "", "k2")


def _gcloud_bin() -> str:
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if found:
        return found
    default = os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd")
    if os.path.exists(default):
        return default
    raise RuntimeError("gcloud is not installed or not on PATH.")


def _gcloud_token() -> str:
    completed = subprocess.run(
        [_gcloud_bin(), "auth", "print-access-token"],
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
    token = (completed.stdout or "").strip()
    if completed.returncode != 0 or not token:
        detail = (completed.stderr or "gcloud auth print-access-token failed").strip()
        raise RuntimeError(detail[:300])
    return token


def vertex_read(evidence: str) -> dict:
    project = os.environ.get("VERTEX_PROJECT", "project-f0b6b4ce-541f-43ff-9f7")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    model = os.environ.get("VERTEX_MODEL", "gemini-2.5-flash")
    try:
        token = _gcloud_token()
    except Exception as exc:
        return {"source": "vertex", "error": str(exc), "safe": False, "paths": []}
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/publishers/google/models/{model}:generateContent"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": READER_SYSTEM + "\n\n" + evidence[:24000]}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
    }
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=90,
    )
    if not response.ok:
        return {"source": "vertex", "error": f"Vertex {response.status_code}: {response.text[:240]}", "safe": False, "paths": []}
    parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "\n".join(part.get("text") or "" for part in parts)
    return _parse_reader(text, "vertex")


def gateway_graph(tree_listing: str, readme_excerpt: str) -> dict:
    """Ask the LLM Gateway for an architecture graph whose ids are real paths."""
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        return {"error": "ASSEMBLYAI_API_KEY is not set", "groups": [], "nodes": [], "edges": []}
    client = OpenAI(base_url="https://llm-gateway.assemblyai.com/v1", api_key=api_key)
    system = (
        "You map a repository. Reply with JSON only: "
        '{"summary":"two sentences","groups":[{"id":"g1","label":"Name"}],'
        '"nodes":[{"id":"n1","label":"Name","path":"real/path.py","group":"g1"}],'
        '"edges":[{"source":"n1","target":"n2","label":"calls"}]}. '
        "At most 8 groups, 24 nodes, 36 edges. Every node.path must be copied from the file list. "
        "Leave out a relationship you are not sure about."
    )
    user = f"README\n{readme_excerpt[:4000]}\n\nFILES\n{tree_listing[:16000]}"
    response = client.chat.completions.create(
        model="qwen3-next-80b-a3b",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1400,
        temperature=0.2,
    )
    parsed = _parse_reader(response.choices[0].message.content or "", "llm_gateway")
    raw = response.choices[0].message.content or ""
    data = {}
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1]) if start >= 0 else {}
    except json.JSONDecodeError:
        data = {}
    return {
        "summary": str(data.get("summary") or parsed.get("summary") or ""),
        "groups": data.get("groups") or [],
        "nodes": data.get("nodes") or [],
        "edges": data.get("edges") or [],
    }


def filter_graph(graph: dict, known_paths: set[str]) -> dict:
    nodes = []
    ids = set()
    for node in graph.get("nodes") or []:
        path = str(node.get("path") or "")
        if path not in known_paths:
            continue
        node_id = str(node.get("id") or path)
        if node_id in ids:
            continue
        ids.add(node_id)
        nodes.append({
            "id": node_id,
            "label": str(node.get("label") or path.split("/")[-1])[:40],
            "path": path,
            "group": str(node.get("group") or ""),
        })
        if len(nodes) >= 24:
            break
    edges = []
    for edge in graph.get("edges") or []:
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in ids and target in ids and source != target:
            edges.append({"source": source, "target": target, "label": str(edge.get("label") or "")[:24]})
        if len(edges) >= 36:
            break
    groups = [group for group in (graph.get("groups") or []) if any(node["group"] == str(group.get("id")) for node in nodes)]
    return {"summary": graph.get("summary") or "", "groups": groups[:8], "nodes": nodes, "edges": edges}


def graph_to_mermaid(graph: dict) -> str:
    lines = ["flowchart LR"]
    group_ids = {str(group.get("id")) for group in graph.get("groups") or []}
    for group in graph.get("groups") or []:
        gid = _mid(str(group.get("id") or "group"))
        lines.append(f'  subgraph {gid}["{_label(group.get("label") or gid)}"]')
        for node in graph.get("nodes") or []:
            if str(node.get("group") or "") == str(group.get("id")):
                lines.append(f'    {_mid(node["id"])}["{_label(node["label"])}"]')
        lines.append("  end")
    for node in graph.get("nodes") or []:
        if str(node.get("group") or "") not in group_ids:
            lines.append(f'  {_mid(node["id"])}["{_label(node["label"])}"]')
    for edge in graph.get("edges") or []:
        label = edge.get("label") or ""
        if label:
            lines.append(f'  {_mid(edge["source"])} -->|{_label(label)}| {_mid(edge["target"])}')
        else:
            lines.append(f'  {_mid(edge["source"])} --> {_mid(edge["target"])}')
    return "\n".join(lines)


def _mid(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "n_" + cleaned
    return cleaned[:40]


def _label(value: str) -> str:
    return str(value).replace('"', "'")[:40]
