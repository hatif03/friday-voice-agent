# Friday — pitch narrative (refined)

Use this for demos, judges, and the deck. Speak it in your own voice; the slides are shorter.

## The moment (problem)

We are in a strange crisis. AI can generate code faster than any team can read it. Humans are still expected to review mountains of diffs, catch logic bugs, and sign off on security—work that does not scale when output is exponential.

At the same time, AI has become very good at *finding* weaknesses: secrets in repos, unsafe patterns, exploit paths. Attackers and automated scanners move at machine speed; reviewers move at human speed. The gap is widening.

If we keep shipping opaque volume without **orientation** and **controlled action**, we risk losing grip on what our systems actually do—and what just got merged.

## What breaks today

- **Review is a bottleneck** — PR queues grow; “LGTM” becomes a coping mechanism, not a guarantee.
- **Context is scattered** — files, history, issues, and architecture live in different tabs; nobody holds the whole shape in their head.
- **Agents act too fast** — auto-issue, auto-comment, auto-merge without a human checkpoint feels powerful until it posts the wrong thing.

## Our bet (solution)

**Friday** is a voice-first **control surface** for a repository you already have open—not another chat box over raw files.

You see a **map** of the repo (entry points, core, hotspots). You **ask out loud**: what changed, what matters, what is risky, what should we track on GitHub. Friday answers from **ingested structure and real GitHub data**, stages issues and comments, and **only posts after you say yes** in a separate turn.

Optional **review intelligence** (Jev + escalation) gives a structured verdict on “is this safe to merge?” instead of vibes.

## One-liner

**Friday helps humans stay in control when code—and threats—move faster than review.**

## Taglines (pick one)

- Talk to the repo. See the shape. Act with consent.
- Voice control for repos in the age of infinite code.
- Map the chaos. Review with judgment. Write only when you mean it.

## Demo URL

https://friday-voice-agent-147606977567.us-central1.run.app/?repo=owner/name

## Demo recording

- Repo: [assets/demo.gif](../assets/demo.gif) (also on README)
- Hosted: https://friday-voice-agent-147606977567.us-central1.run.app/assets/demo.gif (after deploy includes `assets/`)
- Script: [docs/DEMO_SCRIPT.md](DEMO_SCRIPT.md)
