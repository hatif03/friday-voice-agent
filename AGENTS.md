# Voice GitHub Agent — coding agent instructions

## AssemblyAI (required before changing STT / LLM Gateway code)

Before writing or modifying AssemblyAI integration code, read:

- https://www.assemblyai.com/docs/agent-instructions.md — operating rules, models, auth, and gotchas
- https://www.assemblyai.com/docs/llms.txt — documentation index (use to find the right detail pages)

The API changes often — do not rely on memorized parameter names. For deep lookups use `https://www.assemblyai.com/docs/llms-full.txt` (optional `?lang=python` or `?excludeSpec=true`).

Optional on-demand doc search: AssemblyAI docs MCP at `https://assemblyai.com/docs/mcp` (configured in `.cursor/mcp.json`).

## TypeSafe (use the installed skill)

This repo includes the **typesafe-ai** agent skill (see [Agent skill](https://docs.typesafe.ai/agent-skill)). When adding or changing TypeSafe integrations, routing, ranking, extraction, or other structured judgments:

- Ask the agent to **use the TypeSafe skill** (installed at `.agents/skills/typesafe-ai/`; lockfile: `skills-lock.json`).
- Read the live docs index: https://docs.typesafe.ai/llms.txt — do not invent API fields.
- For experiments, use an API key from https://console.typesafe.ai/keys as `TYPESAFE_API_KEY` (server-side only).

Reinstall or update: `npx skills add typesafe-ai/skills --skill typesafe-ai --agent cursor -y` or `npx skills update`.

## IFM K2 Horizon (use the k2-horizon skill)

Hosted docs: [docs.ifm.ai](https://docs.ifm.ai/). Project skill: `.agents/skills/k2-horizon/SKILL.md` — use it when changing `agent.py` or IFM API usage.

| Item | Value |
|------|--------|
| API | `https://api.ifm.ai/v1` — `POST /v1/chat/completions`, `GET /v1/models` |
| Default model | `IFM/K2-Horizon-375B-A23B` (override with `IFM_MODEL`) |
| Env | `AGENT_LLM_PROVIDER=ifm`, `IFM_API_TOKEN` (or `IFM_API_KEY`) |
| Agentic knobs | Top-level `reasoning_effort` (`low`/`medium`/`high`), temperature ≤ 0.3 |

Transcription stays on AssemblyAI Sync (`transcribe.py`); only the tool-calling loop switches provider.

## This repo

FastAPI app (`uvicorn app:app`): the browser holds an AssemblyAI Voice Agent socket (Universal-3.5 Pro, LLM Gateway, spoken replies). Tool calls POST to `/api/voice/tool`. `POST /api/run` remains the Sync STT text fallback. Map ingest is `map_pipeline.py`. Jev is `jev_gate.py`. Gateway, K2, and Vertex second reads are `specialists.py`, and `review_gate.py` is the only verdict check.

| Surface | Implementation | Notes |
|--------|----------------|--------|
| Transcription | Sync API `https://sync.assemblyai.com/transcribe` | `universal-3-5-pro`, raw `Authorization` key (no `Bearer`) |
| Agent | `AGENT_LLM_PROVIDER=assemblyai` → LLM Gateway `qwen3-next-80b-a3b`; `ifm` → K2 Horizon on `api.ifm.ai` | OpenAI Python client in `agent.py` |
| Secrets | `ASSEMBLYAI_API_KEY`, `GITHUB_TOKEN` in `.env` | Never expose keys in `static/` or client-side code |

The `reference/` directory is third-party sample code — not part of the app runtime.

## Conventions

- Python 3.9+, keep server-side AssemblyAI calls in `transcribe.py` and `agent.py`.
- Prefer extending existing patterns over new HTTP clients unless Sync/Gateway cannot cover the use case.
- Voice Agent API (`wss://agents.assemblyai.com`) uses `Authorization: Bearer` — different from Sync STT and LLM Gateway.
