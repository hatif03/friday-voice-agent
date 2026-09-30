# Friday

> Talk to a repository. Friday asks before it writes.

Speak to a GitHub repo on a live **circle-pack map**. AssemblyAI hears you; Friday explains structure, triages activity, and **stages** issues and comments until you say **yes**.

![Voice GitHub Agent Demo](assets/demo.gif)

## What it does

- **Voice and text** — Hold the mic (Ctrl/Option) or use **Ask** on the same brain (`chat.turn`).
- **Repo map** — Landmarks, heat, import arcs, and focus tied to real paths.
- **GitHub read/write** — Commits, issues, PRs, threads; writes need a later confirmation turn.
- **Hybrid agent** — Map tools via orchestrator + Jev; multi-step GitHub via the same [Gateway loop](https://github.com/Sumanth077/Hands-On-AI-Engineering/tree/main/ai_agents/voice-github-agent) as the AssemblyAI tutorial (`agent.run_agent`).

## Docs

| Document | Purpose |
|----------|---------|
| [docs/TEST_QUESTIONS.md](docs/TEST_QUESTIONS.md) | Manual test script (37 scenarios) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Routing, Voice vs Gateway, reliability |
| [hackathon-submission.md](hackathon-submission.md) | Hackathon title, descriptions, extra notes |
| [AGENTS.md](AGENTS.md) | Contributor / agent instructions |
| [docs/presentation/Friday-Voice-Agent.pptx](docs/presentation/Friday-Voice-Agent.pptx) | Slide deck |

## Tech stack

- **FastAPI** + uvicorn
- **AssemblyAI** — Voice Agent (live), Sync STT (`transcribe.py`), LLM Gateway (`agent.py`)
- **GitHub** REST + optional OAuth (`.github_session`, gitignored)
- **D3** circle pack, **marked.js** for markdown replies
- Optional: **TypeSafe Jev**, **IFM K2 Horizon**, Vertex (review escalation)

## Prerequisites

- Python 3.9+
- [AssemblyAI](https://www.assemblyai.com/dashboard/signup) API key
- GitHub token or OAuth app (issues read/write)

## Installation

```bash
git clone https://github.com/hatif03/friday-voice-agent.git
cd friday-voice-agent
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: `ASSEMBLYAI_API_KEY`, `GITHUB_TOKEN` or OAuth client, `GITHUB_REPO=owner/name`.

## Usage

```bash
python app.py
```

Open http://localhost:5000 (optional `?repo=owner/name`).

| Endpoint | Role |
|----------|------|
| Voice WebSocket | Via `GET /api/voice/session` token |
| `POST /api/ask` | Typed questions → `chat.turn` |
| `POST /api/run` | WAV upload → Sync STT → `run_agent` |
| `POST /api/voice/tool` | Voice Agent tool relay |

**Env:** `FRIDAY_GITHUB_GATEWAY` — `multi` (default), `all`, `fallback`, `off`. See `.env.example`.

## Project structure

```
friday-voice-agent/
├── app.py              # FastAPI routes
├── chat.py             # One turn: direct / gateway / Jev / dispatch
├── agent.py            # AssemblyAI Gateway tool loop (8 turns max)
├── orchestrator.py     # Map + GitHub tool handlers
├── voice_broker.py     # Voice Agent bootstrap, friday_turn
├── github_tools.py     # GitHub API + tool schemas
├── map_pipeline.py     # Ingest + circle-pack payload
├── jev_gate.py         # Tool routing confidence
├── transcribe.py       # Sync STT
├── docs/               # Tests, architecture, presentation
├── static/ templates/ prompts/
└── test_friday.py
```

## Testing

```bash
python test_friday.py
```

Manual checklist: [docs/TEST_QUESTIONS.md](docs/TEST_QUESTIONS.md).

## Who decides (reviews)

For merge-safety questions, Jev can accept at ≥0.9 confidence; otherwise Vertex Gemini (K2 if Gemini fails). Details in `review_gate.py` and historical README section in git history.

## License

See repository license file.
