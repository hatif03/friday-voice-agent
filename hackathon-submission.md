# Hackathon submission — Friday

## 1. Submission Title

**Friday: Voice Repo Control**

*(26 characters)*

## 2. Short Description

AI ships code faster than humans can review. Friday is a voice-first map of your repo—explain, scan risk, triage GitHub, and stage writes until you say yes.

*(154 characters)*

## 3. Long Description

We are in an existential squeeze: models generate code at a pace no team can fully review, while AI-driven exploitation of vulnerabilities keeps improving. Humans are still the approval layer—but they no longer see the whole system, only endless diffs and tabs.

**Friday** is a voice-first **control surface** for an open GitHub repository. A circle-pack **map** shows entry points, core files, and hotspots so you grasp shape before depth. You speak or type: explain the landmarks, what changed in the last commit, whether it is safe to merge, scan for security issues, list blockers—or stage an issue or comment. Nothing posts to GitHub until you confirm **yes** on a **separate** turn.

Friday grounds answers in **deterministic ingest** (real paths, imports, landmarks) plus live GitHub data—not a generic chatbot over filenames. AssemblyAI powers live voice; an LLM Gateway tool loop handles multi-step triage; optional review intelligence (Jev with escalation) structures merge-risk answers when confidence is low.

Built for the moment we are in: stay oriented, stay in control, and act deliberately when code and threats both move faster than human review.

*(~1,180 characters)*

## 4. Additional Information

**Problem we pitch:** Infinite AI-generated code vs finite human review; faster offensive AI vs slower defensive understanding; risk of losing control of what actually ships.

**Solution:** Map + voice + grounded tools + human-in-the-loop GitHub writes + optional verdict gate for merge safety.

**Stack:** FastAPI, AssemblyAI (Voice Agent, Sync STT, LLM Gateway), GitHub REST/OAuth, D3, TypeSafe Jev, optional IFM K2 / Vertex.

**Live demo:** https://friday-voice-agent-147606977567.us-central1.run.app/?repo=owner/name

**Demo recording (GIF):** [assets/demo.gif](assets/demo.gif) · https://friday-voice-agent-147606977567.us-central1.run.app/assets/demo.gif

**Local:** `python app.py` — see `docs/DEPLOY.md` for Cloud Run.

**Tests:** `docs/TEST_QUESTIONS.md`, `python test_friday.py`

**Deck:** `docs/presentation/Friday-Voice-Agent.pptx` — narrative in `docs/PITCH.md`

**Env:** `ASSEMBLYAI_API_KEY`, GitHub OAuth or `GITHUB_TOKEN`, `FRIDAY_GITHUB_GATEWAY` (`multi` default), `AGENT_LLM_PROVIDER`

*(~950 characters)*
