---
name: k2-horizon
description: Integrate IFM K2 Horizon models via api.ifm.ai (OpenAI-compatible chat completions, reasoning_effort, tool calling). Use when changing agent.py, IFM API keys, model IDs, or docs at docs.ifm.ai.
---

# IFM K2 Horizon

K2 Horizon is IFM's open model fleet for reasoning, coding, and agentic tool use. Hosted inference: **https://api.ifm.ai/v1**. Product docs: **https://docs.ifm.ai/**.

## Read live docs

Docs are served from [docs.ifm.ai](https://docs.ifm.ai/). Before changing integration code, open the relevant pages there (API reference, errors, model cards). Do not invent request fields.

## API surface (hosted)

| Endpoint | Use |
|----------|-----|
| `POST /v1/chat/completions` | Primary — chat, tools, reasoning |
| `GET /v1/models` | Discover model IDs (e.g. `IFM/K2-Horizon-375B-A23B`) |
| `POST /v1/responses`, `POST /v1/messages` | Not supported (404) |

**Auth:** `IFM_API_TOKEN` or `IFM_API_KEY` (server-side only). Optional override: `IFM_BASE_URL` (default `https://api.ifm.ai/v1`).

## Model IDs

Use exact strings from `GET /v1/models`. Common hosted IDs:

- `IFM/K2-Horizon-375B-A23B` — largest MoE, 512K context, strong agentic performance
- Smaller fleet members (`IFM/K2-Horizon-7B`, `3.7B`, `32B`, etc.) for local/vLLM/SGLang — same chat template conventions

## Agentic requests (tool calling)

- **`messages` content:** plain strings only (no OpenAI content-parts arrays).
- **`tools` / `tool_choice`:** standard OpenAI function schema.
- **`reasoning_effort`:** pass **top-level** `low` | `medium` | `high` (not only inside `chat_template_kwargs` — nested form can drop tool calls at `medium`).
- **Temperature:** ≤ `0.3` for agentic workloads (hosted docs); default in this repo `0.3`.
- **Multi-turn:** when replaying assistant messages, include `reasoning_content` (empty string is valid).

Reasoning trace may appear in `reasoning_content` (and sometimes `reasoning`); final answer in `content`.

## This repository

- Set `AGENT_LLM_PROVIDER=ifm` and `IFM_API_TOKEN` (or `IFM_API_KEY`) in `.env`.
- Optional: `IFM_MODEL`, `IFM_REASONING_EFFORT`, `IFM_TEMPERATURE`, `IFM_BASE_URL`.
- Implementation: `agent.py` (AssemblyAI LLM Gateway remains available with `AGENT_LLM_PROVIDER=assemblyai`).

## Local serving (out of scope unless requested)

vLLM/SGLang: enable `--reasoning-parser k2_horizon` and `--tool-call-parser k2_horizon` for agents. See [K2 Horizon on Hugging Face](https://huggingface.co/IFM) and vLLM recipes.
