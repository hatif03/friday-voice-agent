# Architecture

## Surfaces

| Surface | Entry | Backend |
|---------|--------|---------|
| Live voice | AssemblyAI Voice Agent WebSocket | `friday_turn` → `chat.turn()` |
| Typed Ask | `POST /api/ask` | `chat.turn()` |
| Sync audio fallback | `POST /api/run` | `transcribe.py` → `agent.run_agent()` |
| Map load | `GET /api/map` | `map_pipeline.open_repo()` |

## Turn routing (`chat.turn`)

1. **`command` (`_direct`)** — Yes/no for writes, issue/comment parsers, map shortcuts.
2. **Gateway GitHub** — When `FRIDAY_GITHUB_GATEWAY` is enabled and the utterance is multi-step commit/issue triage, `agent.run_agent()` runs (AssemblyAI LLM Gateway, up to 8 tool rounds).
3. **Jev** — TypeSafe tool choice at confidence ≥ 0.9 for map/repo tools.
4. **K2** — Tool name fallback when Jev is unsure.
5. **`orchestrator.dispatch`** — Handlers for map, review, security, GitHub staging.

Jev selects the tool name; GitHub arguments come from parsers, follow-up state, or the Gateway loop.

## Models

- **Voice session:** LLM Gateway model on stored Voice Agent (`voice_broker.py`).
- **Gateway loop:** `qwen3-next-80b-a3b` (default) or IFM K2 when `AGENT_LLM_PROVIDER=ifm`.
- **Review:** Jev + optional Vertex/K2 via `review_gate.py`.

## Reliability

| Goal | Setup |
|------|--------|
| Map + voice UX | Default: `_direct` + Jev + `FRIDAY_GITHUB_GATEWAY=multi` |
| Heavy GitHub triage | `FRIDAY_GITHUB_GATEWAY=all` or `/api/run` |
| IFM stack | `AGENT_LLM_PROVIDER=ifm` for Gateway |

See `docs/PITCH.md` for product narrative.
