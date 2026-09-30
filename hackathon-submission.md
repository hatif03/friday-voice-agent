# Hackathon submission — Friday

## 1. Submission Title

**Friday: Voice Repo Agent**

*(22 characters)*

## 2. Short Description

Talk to any GitHub repo on a live code map. Friday hears you via AssemblyAI, explains structure, triages issues, and stages writes—only posting after you say yes.

*(159 characters)*

## 3. Long Description

Friday is a voice-first control surface for open-source repositories. Instead of clicking through files, commits, and issues, you hold the mic (or type) and ask in plain language: what does this map mean, where does the app start, what changed last, are there open blockers, or open an issue if something looks wrong.

The UI renders a circle-pack fingerprint of the repository—entry points, core files, and hotspots—so you see shape and heat at a glance. Landmarks anchor explanations; focus and layers (heat, import arcs, line-count sizing) keep the visualization aligned with your question.

Under the hood, Friday combines three ideas. First, **AssemblyAI** powers live conversation: Universal speech models for the Voice Agent session, plus Sync STT and the LLM Gateway for tool-calling when a task needs multiple GitHub steps. Second, **deterministic repo ingest** builds the map and supplies grounded answers for file and architecture questions without hallucinating paths. Third, **human-in-the-loop writes**: creating issues and posting comments only stages a draft until you confirm in a later turn—matching safe agent design for production GitHub accounts.

Friday also supports optional **review intelligence**: structured verdicts for merge-risk questions, with escalation when confidence is low. GitHub OAuth lets signed-in users act on their own repos while keeping tokens server-side.

Built for hackathons and daily triage: one URL, one repo, hands-free check-ins before standup or while reviewing a teammate’s project.

*(~1,450 characters — room for edits within 2,000 limit)*

## 4. Additional Information

**Stack:** FastAPI, AssemblyAI Voice Agent + Sync STT + LLM Gateway (`qwen3-next-80b-a3b` in the reference loop; voice broker model configurable), GitHub REST API, D3 circle pack, optional IFM K2 Horizon and TypeSafe Jev for routing and review.

**Demo flow:** Open `http://localhost:5000/?repo=owner/name` → explore map → hold mic → “Explain the landmarks” → “What changed in the latest commit?” → “Open an issue titled …” → “yes” to post.

**Docs in repo:** `README.md`, `AGENTS.md`, `docs/TEST_QUESTIONS.md`, `docs/ARCHITECTURE.md`.

**Test checklist:** See `docs/TEST_QUESTIONS.md` (37 scenarios). Run `python test_friday.py` for automated coverage.

**Env highlights:** `ASSEMBLYAI_API_KEY`, `GITHUB_TOKEN` or OAuth, `GITHUB_REPO`, `AGENT_LLM_PROVIDER` (`assemblyai` | `ifm`), `FRIDAY_GITHUB_GATEWAY` (`multi` | `all` | `off`).

**Reliability note (Jev vs reference agent):** Jev picks a *single* tool name quickly; GitHub *arguments* (issue title, body, number) come from parsers and follow-up state—or from the AssemblyAI Gateway multi-tool loop (`agent.run_agent`), like the [Hands-On AI Engineering voice-github-agent](https://github.com/Sumanth077/Hands-On-AI-Engineering/tree/main/ai_agents/voice-github-agent). Map-specific tools still need the orchestrator. The most reliable all-around setup is a **hybrid**: Voice Agent → `friday_turn` → direct parsers for yes/no and writes; Gateway loop for multi-step GitHub triage; K2 only when Jev confidence is low for *map* routing—not as a replacement for Gateway tool JSON on writes. Setting `FRIDAY_GITHUB_GATEWAY=all` moves most GitHub utterances to the reference loop; dropping Jev entirely would hurt fast, cheap routing to `explain_file`, `list_landmarks`, and map layers unless every utterance goes through a full 8-turn agent (higher latency and cost).

**Presentation:** `docs/presentation/Friday-Voice-Agent.pptx`

*(~1,650 characters)*
