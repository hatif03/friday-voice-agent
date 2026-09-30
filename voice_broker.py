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
        "name": "friday_turn",
        "description": "Call this for every user utterance. Pass the utterance. Speak only the returned say field.",
        "parameters": {
            "type": "object",
            "properties": {
                "utterance": {"type": "string", "description": "The user's words, unchanged."},
            },
            "required": ["utterance"],
        },
        "execution_mode": "hold",
        "timeout_seconds": 60,
        "response_instructions": {
            "success": "Speak only the say field, then stop.",
            "error": "Say that the turn failed, in one sentence.",
        },
    },
]



def _auth_headers() -> dict:
    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def system_prompt() -> str:
    """Base instructions plus the repository already on screen, when there is one."""
    base = read_prompt("voice_system.txt").rstrip()
    try:
        from github_tools import active_repo
        import map_pipeline

        slug = active_repo()
    except Exception:
        return base
    if not slug or "/" not in slug:
        return base
    owner, repo = slug.split("/", 1)
    lines = [
        "",
        f"The repository already open is {owner}/{repo}.",
        f"The owner is {owner}. The repository name is {repo}.",
        "Pass every utterance to friday_turn. Do not answer it yourself.",
    ]
    cached = map_pipeline.get_cached(slug)
    stats = (cached or {}).get("stats") or {}
    if stats.get("files"):
        lines.append(f"The map has {stats.get('files')} files and {stats.get('loc') or 0} lines.")
    return base + "\n" + "\n".join(lines)


def spoken_greeting() -> str:
    """Spoken as written. Name the repository already on screen."""
    try:
        from github_tools import active_repo

        slug = active_repo()
    except Exception:
        slug = ""
    if not slug or "/" not in slug:
        return "Name a repository, or ask what is open. I ask before I write anything to GitHub."
    owner, repo = slug.split("/", 1)
    return f"{repo} is open. It belongs to {owner}. Ask me about this map."


def repo_keyterms() -> list:
    try:
        from github_tools import active_repo

        slug = active_repo()
    except Exception:
        return []
    if not slug or "/" not in slug:
        return []
    owner, repo = slug.split("/", 1)
    return [owner, repo, slug]


_VOICE_CANDIDATES = ("claude-haiku-4-5", "claude-sonnet-4-6")
_voice_model = ""


def voice_llm_model() -> str:
    """A gateway model that accepts tools. The fast Qwen model does not."""
    global _voice_model
    override = (os.environ.get("VOICE_AGENT_MODEL") or "").strip()
    if override:
        return override
    if _voice_model:
        return _voice_model
    from openai import OpenAI

    client = OpenAI(
        base_url="https://llm-gateway.assemblyai.com/v1",
        api_key=os.environ["ASSEMBLYAI_API_KEY"],
    )
    probe = [
        {
            "type": "function",
            "function": {
                "name": "friday_turn",
                "description": "Relay one utterance.",
                "parameters": {
                    "type": "object",
                    "properties": {"utterance": {"type": "string"}},
                    "required": ["utterance"],
                },
            },
        }
    ]
    for model in _VOICE_CANDIDATES:
        try:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say hi."}],
                tools=probe,
                tool_choice="auto",
                max_tokens=16,
            )
        except Exception:
            continue
        _voice_model = model
        return model
    _voice_model = _VOICE_CANDIDATES[0]
    return _voice_model


def _agent_body() -> dict:
    return {
        "name": "Friday",
        "voice": {"voice_id": VOICE},
        "system_prompt": system_prompt(),
        "greeting": spoken_greeting(),
        "tools": VOICE_TOOLS,
        "input": _input_config(),
        "output": {"format": {"encoding": "audio/pcm"}, "volume": 100},
        "llm": [
            {
                "base_url": "https://llm-gateway.assemblyai.com/v1",
                "model": voice_llm_model(),
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
    for term in repo_keyterms() + list(keyterms or []):
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
            "vad_threshold": 0.35,
            "min_silence": 320,
            "max_silence": 900,
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
                "system_prompt": system_prompt(),
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
