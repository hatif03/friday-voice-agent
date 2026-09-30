# Friday — 3-minute demo script

**Before you record**

- Open: `https://friday-voice-agent-147606977567.us-central1.run.app/?repo=YOUR_OWNER/YOUR_REPO` (pick a repo you know: landmarks, a few commits, maybe open issues).
- Sign in to GitHub in the app if you will post an issue.
- Hard refresh (Ctrl+Shift+R). Mic permission allowed.
- Collapse or ignore the “steps” trace on screen unless you want one quick flash—judges care about **what Friday says**, not every tool name.
- Have a **second browser tab** ready on that repo’s GitHub issues page (you’ll switch to it once after “yes”).

**Format:** Mix **voice** (hold mic) and **Ask** (type) if voice glitches—same backend. Below assumes mostly voice.

---

## 0:00–0:20 — Hook (talking head or full-screen app loading)

**You say:**

> AI writes code faster than any team can review it. Friday is how you stay oriented: you open a repo, you see its shape on a map, you ask out loud what matters—and nothing hits GitHub until you say yes.

**On screen:** Paste URL with `?repo=…` and hit Enter. Let the circle map load.

---

## 0:20–0:50 — See the shape (map + one question)

**On screen:** Pan/zoom the map slightly. Point at a large circle or hotspot if you have one.

**You say (voice or Ask):**

> “Explain this map to me.”

**Wait for answer.** Read one sentence from the reply if it’s long.

**You say:**

> Instead of fifty tabs, you get entry points, core files, and hotspots in one view.

**Optional (only if fast):** “What are the landmarks?” — then skip reading the full list; gesture at the sidebar.

---

## 0:50–1:20 — Ground in GitHub (one read, not a tour)

**You say (voice):**

> “What changed in the latest commit?”

**On screen:** Let the answer appear. Don’t expand “steps.”

**You say:**

> That’s real history from GitHub—not a guess from a generic chatbot.

**Skip:** listing all issues, PRs, and commits. One read is enough for three minutes.

---

## 1:20–1:45 — Risk / judgment (pick ONE line)

**Option A — security (good for pitch):**

**You say:**

> “Scan this repository for security issues.”

**You say after reply:**

> Friday surfaces what it finds; you still decide what to do.

**Option B — merge (if your repo has a recent commit you trust):**

**You say:**

> “Review the latest commit. Is it safe to merge?”

**You say after reply:**

> Structured judgment—not just vibes.

Use **only A or B**, not both.

---

## 1:45–2:25 — Human in the loop (the money shot)

**You say (voice or Ask, one clear sentence):**

> “Open an issue titled Friday demo video.”

**On screen:** Answer must include **have not posted** / draft language.

**You say to camera:**

> Notice it did **not** post. It staged a draft. That’s intentional.

**Pause 2 seconds.**

**You say (new turn—release mic first if you used voice):**

> “Yes.”

**On screen:** “Posted issue …” with link.

**You say:**

> Separate turn. Separate consent. That’s the control surface we want in the age of infinite code.

**On screen:** Click **Open it on GitHub** (or switch to your issues tab) for two seconds to prove it’s real.

---

## 2:25–2:55 — Close

**On screen:** Back to map + chat.

**You say:**

> Friday doesn’t replace your judgment. It gives you a map, a voice, and a hard stop before anything leaves the building. Try it on your repo—the link is in the README.

**On screen (optional end card):**  
`friday-voice-agent-147606977567.us-central1.run.app`  
`github.com/hatif03/friday-voice-agent`

---

## If something breaks (don’t ruin the take)

| Problem | Fallback |
|--------|----------|
| Voice won’t connect | Type the same lines in **Ask** |
| Issue post fails (no OAuth) | Stop after draft: “In production you’d sign in once; the draft still proves the gate.” |
| Slow answer | Cut to B-roll of map while waiting; trim in edit |
| Wrong repo / empty map | Use a repo you’ve tested from `docs/TEST_QUESTIONS.md` |

---

## Phrases to **not** use on camera (same-turn trap)

- Don’t say: “Open an issue titled X **and yes post it**” in one breath.
- Don’t demo comment + issue + landmarks + architecture in one recording.

---

## One-line cheat sheet (tape on monitor)

1. Hook → load map  
2. Explain this map  
3. Latest commit  
4. Security **or** safe to merge  
5. Open issue titled Friday demo video → **yes** → show GitHub  
6. Close: orientation + consent  

**Target length:** 2:45–3:15 with natural pauses.
