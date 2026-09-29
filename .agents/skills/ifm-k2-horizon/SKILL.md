---
name: ifm-k2-horizon
description: >-
  Integrate IFM K2 Horizon models via the OpenAI-compatible api.ifm.ai endpoint.
  Use when changing the voice agent LLM, tool-calling loop, reasoning_effort,
  or debugging IFM chat completions in this repo.
---

# IFM K2 Horizon

Hosted API: `https://api.ifm.ai/v1` (override with `IFM_BASE_URL`).

**Live docs:** https://docs.ifm.ai/ — read in the browser or via your agent’s fetch tools. There is no plain-text `llms.txt` mirror; do not invent request fields.

## Auth

- `IFM_API_TOKEN` (preferred) or `IFM_API_KEY` in server env only.
- OpenAI client: `OpenAI(base_url="https://api.ifm.ai/v1", api_key=...)`.

## Models (exact IDs)

Use `GET /v1/models` for the current catalog. Common K2 Horizon IDs:

- `IFM/K2-Horizon-375B-A23B` — flagship MoE, 512K context, strong tool use
- `IFM/K2-Horizon-32B`, `IFM/K2-Horizon-7B`, `IFM/K2-Horizon-3.7B` — smaller fleet members

## Chat completions (agent loop)

- Endpoint: `POST /v1/chat/completions` only (not `/v1/responses` or `/v1/messages`).
- **Messages:** plain string `content` per role — no content-parts arrays.
- **Tools:** standard OpenAI function schemas; `tool_choice` supported.
- **Reasoning:** pass top-level `reasoning_effort`: `low` | `medium` | `high` (not inside `chat_template_kwargs` for tool calls — that form can drop tool payloads at `medium`).
- **Agentic sampling:** prefer `temperature` ≤ 0.3 (docs); avoid tuning both `temperature` and `top_p`.
- **Multi-turn:** replayed assistant messages must include `reasoning_content` (empty string is fine) when continuing after tool calls.

Thinking traces appear in `reasoning_content` (and sometimes `reasoning`); final answer in `content`.

## This repository

- Provider switch: `AGENT_LLM_PROVIDER=ifm` (auto-selected if only IFM keys are set).
- Implementation: `agent.py` — same GitHub tool loop as AssemblyAI LLM Gateway.
- Transcription stays on AssemblyAI Sync STT (`transcribe.py`); only the reasoning model changes.

## Local / self-host

For vLLM or SGLang, enable `--reasoning-parser k2_horizon` and `--tool-call-parser k2_horizon`. See [K2 Horizon on Hugging Face](https://huggingface.co/IFM/K2-Horizon-375B-A23B) and [vLLM recipes](https://recipes.vllm.ai/IFM/K2-Horizon-3.7B).
