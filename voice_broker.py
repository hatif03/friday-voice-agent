"""AssemblyAI Voice Agent session: stored agent on the LLM Gateway, browser token, tool list."""
import os

import requests


def read_prompt(name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()

AGENTS_ROOT = "https://agents.assemblyai.com"
AGENT_ID_PATH = ".friday_agent_id"
VOICE = "anna"

VOICE_TOOLS = [
    {
        "type": "function",
        "name": "open_repository",
        "description": "Call this when the user names a GitHub repository to open, or says to look at owner/name. Downloads the tree and draws the map.",
        "parameters": {
            "type": "object",
            "properties": {"repo": {"type": "string", "description": "Repository as owner/name."}},
            "required": ["repo"],
        },
        "execution_mode": "hold",
        "timeout_seconds": 180,
    },
    {
        "type": "function",
        "name": "describe_map",
        "description": "Call this when the user asks what they are looking at, for a tour, or for the shape of the open repository.",
        "parameters": {"type": "object", "properties": {}},
        "execution_mode": "hold",
        "timeout_seconds": 30,
    },
    {
        "type": "function",
        "name": "focus_file",
        "description": "Call this when the user names a file or asks to show, open, or zoom to a path on the map.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Repository-relative file path."}},
            "required": ["path"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "list_landmarks",
        "description": "Call this when the user asks which files matter, or for entry points, core modules, or hotspots.",
        "parameters": {"type": "object", "properties": {}},
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "set_map_layer",
        "description": "Call this when the user wants heat, import edges, or line-count sizing turned on or off.",
        "parameters": {
            "type": "object",
            "properties": {
                "layer": {"type": "string", "enum": ["heat", "edges", "loc"]},
                "enabled": {"type": "boolean"},
            },
            "required": ["layer", "enabled"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "review_changes",
        "description": "Call this when the user asks if a change is risky, safe, dangerous, or wants the latest commit or a pull request reviewed.",
        "parameters": {
            "type": "object",
            "properties": {
                "sha": {"type": "string", "description": "Commit SHA. Omit to review the latest commit."},
                "pr_number": {"type": "integer", "description": "Pull request number, if they named one."},
            },
        },
        "execution_mode": "hold",
        "timeout_seconds": 180,
        "response_instructions": {
            "success": "Speak the say field. If cleared is false, do not say the change is safe.",
            "error": "Say that the review failed and why, in one sentence.",
        },
    },
    {
        "type": "function",
        "name": "explain_architecture",
        "description": "Call this when the user asks how the code fits together, for an architecture diagram, or for the big picture beyond the fingerprint.",
        "parameters": {"type": "object", "properties": {}},
        "execution_mode": "hold",
        "timeout_seconds": 180,
    },
    {
        "type": "function",
        "name": "list_recent_commits",
        "description": "Call this when the user asks what changed recently or for the latest commits.",
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer", "description": "How many commits, max 20."}},
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "list_open_issues",
        "description": "Call this when the user asks about open issues.",
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "list_pull_requests",
        "description": "Call this when the user asks about open pull requests.",
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "create_issue",
        "description": "Stage a GitHub issue. Does not post it. Ask the user to say yes, then call confirm_write on a later turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["title"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "add_comment",
        "description": "Stage a comment on an issue or pull request. Does not post it. Ask the user to say yes, then call confirm_write on a later turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "body": {"type": "string"},
            },
            "required": ["issue_number", "body"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "confirm_write",
        "description": "Post or discard the staged issue or comment. Call only after the user says yes or no in a new turn.",
        "parameters": {
            "type": "object",
            "properties": {"confirmed": {"type": "boolean"}},
            "required": ["confirmed"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "scrub_history",
        "description": "Load the recent commit timeline and light the files those commits touched. count is how many commits, up to 80. index pauses on one commit. play lights the latest commits.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "index": {"type": "integer"},
                "play": {"type": "boolean"},
            },
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "who_touched",
        "description": "List the authors who committed a file. Only names that GitHub returned. path is a file path on the map.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "explain_fix",
        "description": "Follow an issue number such as fixes #12 to the pull request that closed it, highlight introduced and fixing files, and score the fixing diff. Do not invent a root cause.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "read_thread",
        "description": "Read an issue or pull request thread, including comments. kind is issue or pull. Summarize in speech; the full thread stays on screen.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["issue", "pull"]},
                "number": {"type": "integer"},
            },
            "required": ["kind", "number"],
        },
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "scan_noise",
        "description": "Find likely spam or repeated issues. List them. Never close, hide, or delete anything.",
        "parameters": {"type": "object", "properties": {}},
        "execution_mode": "hold",
    },
    {
        "type": "function",
        "name": "scan_security",
        "description": "Check the open map for likely secrets, risky calls, a missing license, and dependency advisories. Report them. Never fix or close anything.",
        "parameters": {"type": "object", "properties": {}},
        "execution_mode": "hold",
        "timeout_seconds": 90,
    },
    {
        "type": "function",
        "name": "ask_repository",
        "description": "Answer a question about the open repository from the files already on the map. Use this when the user asks how something works and no other tool fits.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
        "execution_mode": "hold",
        "timeout_seconds": 60,
    },
]


def _auth_headers() -> dict:
    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _agent_body() -> dict:
    return {
        "name": "Friday",
        "voice": {"voice_id": VOICE},
        "system_prompt": read_prompt("voice_system.txt"),
        "greeting": "AI writes the mountain. I keep you in charge of what ships. Name a repository, or ask what is open.",
        "tools": VOICE_TOOLS,
        "input": _input_config(),
        "output": {"format": {"encoding": "audio/pcm"}, "volume": 100},
        "llm": [
            {
                "base_url": "https://llm-gateway.assemblyai.com/v1",
                "model": "qwen3.5-4b-32k-fast",
                "api_key": os.environ["ASSEMBLYAI_API_KEY"],
            }
        ],
    }


def _require_tools(agent_id: str, headers: dict) -> None:
    probe = requests.get(f"{AGENTS_ROOT}/v1/agents/{agent_id}", headers=headers, timeout=30)
    if not probe.ok:
        raise RuntimeError(f"Could not read the Voice Agent ({probe.status_code}): {probe.text[:400]}")
    saved = probe.json().get("tools") or []
    if len(saved) < len(VOICE_TOOLS):
        raise RuntimeError("The Voice Agent was saved without its tools.")


def _save_agent(method: str, url: str, headers: dict):
    body = _agent_body()
    response = requests.request(method, url, headers=headers, json=body, timeout=30)
    if not response.ok:
        raise RuntimeError(f"Could not save the Voice Agent ({response.status_code}): {response.text[:400]}")
    payload = response.json()
    agent_id = payload.get("id") or url.rstrip("/").split("/")[-1]
    _require_tools(agent_id, headers)
    return response


def ensure_stored_agent() -> str:
    """Create or reuse a stored Voice Agent whose brain is the LLM Gateway."""
    headers = _auth_headers()
    agent_id = ""
    if os.path.exists(AGENT_ID_PATH):
        agent_id = open(AGENT_ID_PATH, encoding="utf-8").read().strip()
    if agent_id:
        probe = requests.get(f"{AGENTS_ROOT}/v1/agents/{agent_id}", headers=headers, timeout=30)
        if probe.ok:
            _save_agent("PUT", f"{AGENTS_ROOT}/v1/agents/{agent_id}", headers)
            return agent_id
    created = _save_agent("POST", f"{AGENTS_ROOT}/v1/agents", headers)
    agent_id = created.json()["id"]
    with open(AGENT_ID_PATH, "w", encoding="utf-8") as handle:
        handle.write(agent_id)
    return agent_id


def mint_token() -> str:
    response = requests.get(
        f"{AGENTS_ROOT}/v1/token",
        headers=_auth_headers(),
        params={"expires_in_seconds": 300, "max_session_duration_seconds": 3600},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Voice token failed ({response.status_code}): {response.text[:300]}")
    payload = response.json()
    token = payload.get("token") or payload.get("temp_token")
    if not token:
        raise RuntimeError("Voice token response had no token.")
    return token


def _input_config(keyterms: list[str] | None = None) -> dict:
    terms = ["Friday", "hotspot", "blast radius", "GitHub"]
    for term in keyterms or []:
        if term not in terms:
            terms.append(term)
    return {
        "format": {"encoding": "audio/pcm"},
        "keyterms": terms[:100],
        "continuous_partials": True,
        "transcription_mode": "balanced",
        "voice_focus": "near-field",
        "transcription_prompt": "A developer speaking about a GitHub repository, file paths, commits, pull requests, and code review.",
        "turn_detection": {
            "vad_threshold": 0.5,
            "min_silence": 700,
            "max_silence": 2400,
            "interrupt_response": True,
        },
    }


def session_update(agent_id: str, keyterms: list[str] | None = None) -> dict:
    """The first message may contain only agent_id. Other fields are a later update."""
    return {
        "bind": {"type": "session.update", "session": {"agent_id": agent_id}},
        "configure": {
            "type": "session.update",
            "session": {
                "system_prompt": read_prompt("voice_system.txt"),
                "tools": VOICE_TOOLS,
                "input": _input_config(keyterms),
            },
        },
    }


def browser_bootstrap(keyterms: list[str] | None = None) -> dict:
    agent_id = ensure_stored_agent()
    token = mint_token()
    update = session_update(agent_id, keyterms)
    return {
        "token": token,
        "ws_url": f"wss://agents.assemblyai.com/v1/ws?token={token}",
        "session": update["bind"],
        "configure": update["configure"],
        "hold_tools": [tool["name"] for tool in VOICE_TOOLS if tool.get("execution_mode") == "hold"],
    }
