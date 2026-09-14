"""Agent loop: tool-calling GitHub agent over an OpenAI-compatible API.

Backends (AGENT_LLM_PROVIDER):
  - assemblyai — LLM Gateway, qwen3-next-80b-a3b (default)
  - ifm — IFM K2 Horizon on api.ifm.ai (docs.ifm.ai)

Docs:
  https://www.assemblyai.com/docs/llm-gateway/quickstart
  https://docs.ifm.ai/
"""
import json
import os

from openai import OpenAI

from github_tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

ASSEMBLYAI_MODEL = "qwen3-next-80b-a3b"
IFM_DEFAULT_MODEL = "IFM/K2-Horizon-375B-A23B"
MAX_TURNS = 8  # safety cap so a confused model can't loop forever

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
with open(_PROMPT_PATH, encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()


def _llm_provider() -> str:
    return (os.environ.get("AGENT_LLM_PROVIDER") or "assemblyai").strip().lower()


def _client() -> OpenAI:
    provider = _llm_provider()
    if provider == "ifm":
        api_key = os.environ.get("IFM_API_TOKEN") or os.environ.get("IFM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "IFM_API_TOKEN or IFM_API_KEY is not set. Check your .env file."
            )
        base_url = os.environ.get("IFM_BASE_URL", "https://api.ifm.ai/v1")
        return OpenAI(base_url=base_url, api_key=api_key)

    if provider != "assemblyai":
        raise RuntimeError(
            f"Unknown AGENT_LLM_PROVIDER '{provider}'. Use 'assemblyai' or 'ifm'."
        )

    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set. Check your .env file.")
    return OpenAI(base_url="https://llm-gateway.assemblyai.com/v1", api_key=api_key)


def _chat_model() -> str:
    if _llm_provider() == "ifm":
        return os.environ.get("IFM_MODEL", IFM_DEFAULT_MODEL)
    return ASSEMBLYAI_MODEL


def _completion_kwargs() -> dict:
    if _llm_provider() != "ifm":
        return {"max_tokens": 2000}

    effort = (os.environ.get("IFM_REASONING_EFFORT") or "high").strip().lower()
    if effort not in ("low", "medium", "high"):
        raise RuntimeError("IFM_REASONING_EFFORT must be low, medium, or high.")

    temperature = float(os.environ.get("IFM_TEMPERATURE", "0.3"))
    return {
        "max_tokens": int(os.environ.get("IFM_MAX_TOKENS", "2000")),
        "temperature": temperature,
        "extra_body": {"reasoning_effort": effort},
    }


def _assistant_message_for_history(message) -> dict:
    """IFM requires reasoning_content on replayed assistant turns ("" is fine)."""
    payload = message.model_dump(exclude_none=True)
    if _llm_provider() == "ifm" and "reasoning_content" not in payload:
        payload["reasoning_content"] = getattr(message, "reasoning_content", None) or ""
    return payload


def run_agent(spoken_instruction: str) -> dict:
    """Runs the tool-calling loop. Returns a dict with the agent's final
    summary text and the list of tool calls made along the way, each as
    {"name": str, "args": dict, "result": Any}."""
    client = _client()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": spoken_instruction},
    ]
    tool_call_log = []

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=_chat_model(),
            messages=messages,
            tools=TOOL_SCHEMAS,
            **_completion_kwargs(),
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls

        if not tool_calls:
            return {
                "summary": message.content or "(no summary returned)",
                "tool_calls": tool_call_log,
            }

        # Record the assistant's tool-call request in the conversation history.
        messages.append(_assistant_message_for_history(message))

        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            print(f"  -> calling tool: {name}({args})")
            fn = TOOL_FUNCTIONS.get(name)
            if fn is None:
                result = {"error": f"Unknown tool '{name}'"}
            else:
                try:
                    result = fn(**args)
                except Exception as exc:  # tool errors get fed back to the model, not raised
                    result = {"error": str(exc)}

            tool_call_log.append({"name": name, "args": args, "result": result})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

    return {
        "summary": "Stopped after reaching the turn limit without a final answer — check the tool calls above.",
        "tool_calls": tool_call_log,
    }
