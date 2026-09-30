# Architecture

## Surfaces

| Surface | Entry | Backend |
|---------|--------|---------|
| Live voice | AssemblyAI Voice Agent WebSocket | `friday_turn` → `chat.turn()` |
| Typed Ask | `POST /api/ask` | `chat.turn()` |
| Sync audio fallback | `POST /api/run` | `transcribe.py` → `agent.run_agent()` |
| Map load | `GET /api/map` | `map_pipeline.open_repo()` |

## Turn routing (`chat.turn`)

1. **`command` (`_direct`)** — Unambiguous phrases: yes/no for `confirm_write`, issue/comment parsers, map shortcuts, landmark list, layers, etc.
2. **Gateway GitHub** — When `FRIDAY_GITHUB_GATEWAY` is not `off` and the utterance is multi-step commit/issue triage, `agent.run_agent()` runs (reference-style loop).
3. **Jev** — TypeSafe tool choice at confidence ≥ 0.9 for map/repo tools.
4. **K2** — Tool name only when Jev is unsure (`specialists.k2_choose_tool`).
5. **`orchestrator.dispatch`** — One handler per tool; GitHub writes stage until `confirm_write`.

Jev does **not** fill GitHub tool arguments. Parsers and pending state (`_PENDING_ISSUE_AWAITING`, `_PENDING_COMMENT_ON`) handle follow-up turns. Failed `create_issue` / `add_comment` can fall back to Gateway when enabled.

## Voice vs reference demo

The [reference voice-github-agent](https://github.com/Sumanth077/Hands-On-AI-Engineering/tree/main/ai_agents/voice-github-agent) uses **Sync STT + Gateway tool loop only**. Friday adds a **map orchestrator** and **Voice Agent** for low-latency speech. Shared code: `agent.py`, `github_tools.py`, `prompts/system_prompt.txt`.

## Models

- **Voice session:** LLM Gateway model on stored Voice Agent (`voice_broker.py`).
- **Gateway loop:** `qwen3-next-80b-a3b` (default in `agent.py`) or IFM K2 when `AGENT_LLM_PROVIDER=ifm`.
- **Jev / review:** TypeSafe + optional Vertex/K2 per `review_gate.py` / `jev_gate.py`.

## Reliability recommendations

| Goal | Setup |
|------|--------|
| Best map + voice UX | Default: Jev + `_direct` + `FRIDAY_GITHUB_GATEWAY=multi` |
| Best GitHub-only reliability | `/api/run` or `FRIDAY_GITHUB_GATEWAY=all` |
| IFM stack | `AGENT_LLM_PROVIDER=ifm` for Gateway; keep Jev for map routing |
| Drop Jev entirely | Possible only if every turn uses `run_agent` + expanded tool schemas for map tools—higher latency; not recommended for hackathon demo |

See `hackathon-submission.md` § Additional Information for the full tradeoff.
