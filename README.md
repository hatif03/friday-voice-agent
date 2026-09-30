# Friday

> **Map the chaos. Review with judgment. Act only when you mean it.**

AI generates code faster than humans can review it. Vulnerabilities are hunted at machine speed. Friday is a **voice-first control surface** for the repository you already have open: a live **code map**, grounded answers, security and merge-risk checks, and **GitHub writes that wait for your yes**.

**Live demo:** https://friday-voice-agent-147606977567.us-central1.run.app  
Add `?repo=owner/name` (e.g. `hatif03/midnight-pool`).

![Friday demo walkthrough](assets/demo.gif)

Recording also at `/assets/demo.gif` when the app is running (local or Cloud Run).

## Why Friday exists

We are asked to review mountains of AI-generated code with human bandwidth. That does not scale. Meanwhile, automated exploitation of weak code keeps getting better. Friday does not replace judgment—it **orients** you: where the repo starts, what changed, what is hot, what might be unsafe, and what to file on GitHub—without silent auto-posting.

## What you get

| Capability | What it means |
|------------|----------------|
| **Circle-pack map** | Entry points, core files, hotspots—shape at a glance |
| **Voice + Ask** | Same brain (`chat.turn`); hold mic or type |
| **Grounded Q&A** | Landmarks, files, architecture, commits, issues, PRs |
| **Staged writes** | Issues/comments draft first; **yes** on a **later** turn posts |
| **Review gate** | Structured merge-risk narrative when you ask |
| **Security scan** | Repo checks surfaced in conversation |

## Docs

| Document | Purpose |
|----------|---------|
| [docs/PITCH.md](docs/PITCH.md) | Problem / solution narrative for judges |
| [docs/TEST_QUESTIONS.md](docs/TEST_QUESTIONS.md) | Manual test script (37 scenarios) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Routing and reliability |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Google Cloud Run deploy |
| [hackathon-submission.md](hackathon-submission.md) | Form-ready copy |
| [docs/presentation/Friday-Voice-Agent.pptx](docs/presentation/Friday-Voice-Agent.pptx) | YC-style deck |
| [assets/demo.gif](assets/demo.gif) | Product walkthrough GIF |

## Tech stack

- **FastAPI** + uvicorn
- **AssemblyAI** — Voice Agent, Sync STT, LLM Gateway tool loop
- **GitHub** REST + OAuth
- **D3** map, optional **TypeSafe Jev**, **IFM K2**, Vertex for review escalation

## Run locally

```bash
git clone https://github.com/hatif03/friday-voice-agent.git
cd friday-voice-agent
python -m venv venv && pip install -r requirements.txt
cp .env.example .env   # ASSEMBLYAI_API_KEY, GitHub OAuth or token
python app.py
```

http://localhost:5000/?repo=owner/name

## Redeploy (Cloud Run)

```bash
python scripts/deploy_cloudrun.py --project YOUR_GCP_PROJECT
```

## Test

```bash
python test_friday.py
```

## License

See repository license file.
