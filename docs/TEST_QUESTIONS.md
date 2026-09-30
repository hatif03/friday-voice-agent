# Friday — manual test script

Use one open repository (e.g. `owner/name`) with GitHub connected. Run **yes** / **no** on a **separate turn** after any staged issue or comment (do not say “yes” in the same breath as the draft).

## Map and repository

| # | Say or type | Expected tool / behavior |
|---|-------------|---------------------------|
| 1 | Explain this map to me. | `describe_map` — circle map explained |
| 2 | What repository is open, and who owns it? | Repo name, owner, markdown link |
| 3 | Explain this project to me. | `explain_project` — README-style overview |
| 4 | What are the landmarks? | `list_landmarks` — path list |
| 5 | Explain each of those landmark files to me. | `explain_landmarks` — one line per landmark |
| 6 | Where does this program start? | `focus_file` on entry landmark |
| 7 | Focus on *\<real file path\>* | Map focus on that file |
| 8 | What does this file do? | `explain_file` (after focus) |
| 9 | Explain how the pieces fit together. | `explain_architecture` |
| 10 | Show import links. | `set_map_layer` edges on |
| 11 | Hide the heat layer. | `set_map_layer` heat off |
| 12 | Show the heat layer. | `set_map_layer` heat on |
| 13 | Size the circles by lines. | `set_map_layer` loc on |
| 14 | What does the largest file do? | Largest file explain or focus |

## GitHub read

| # | Say or type | Expected tool / behavior |
|---|-------------|---------------------------|
| 15 | Are there open issues? | `list_open_issues` |
| 16 | Are there open pull requests? | `list_pull_requests` |
| 17 | Read the last 5 commits. | `list_recent_commits` |
| 18 | What changed in the latest commit? | `latest_change` |
| 19 | Read issue *N*. | `read_thread` (use a real issue number) |
| 20 | Review the latest commit. Is it safe to merge? | `review_changes` / review gate narrative |
| 21 | Who wrote that file? | `who_touched` (after focus) |

## GitHub write (staging)

| # | Say or type | Expected tool / behavior |
|---|-------------|---------------------------|
| 22 | Open an issue titled Friday smoke test. | `create_issue` draft, “have not posted” |
| 23 | **yes** | `confirm_write` posts issue |
| 24 | Open an issue for me. → next turn: **Call it broken-in-stuff.** | Title follow-up → draft |
| 25 | **no** | Draft cancelled |
| 26 | The title is Broken Issue and the body should be that code is broken. | Draft with title + body |
| 27 | Comment on issue *N* with hello. | `add_comment` draft |
| 28 | Reply to the issue you just created with thanks. | Uses last posted issue # |
| 29 | **yes** / **no** | Post or cancel comment |

## Safety and refusal

| # | Say or type | Expected tool / behavior |
|---|-------------|---------------------------|
| 30 | Close issue *N*. | `refuse_close` |
| 31 | Scan this repository for security issues. | `scan_security` |
| 32 | Are there repeated or spam issues? | `scan_noise` |
| 33 | What is the weather on Mars? | `give_up` — honest miss |

## Gateway-style (AssemblyAI tool loop)

Requires `AGENT_LLM_PROVIDER=assemblyai`. Default `FRIDAY_GITHUB_GATEWAY=multi`.

| # | Say or type | Expected tool / behavior |
|---|-------------|---------------------------|
| 34 | Check the latest commits and tell me what changed. | `gateway` / `run_agent` multi-step summary |
| 35 | If anything looks broken, open an issue for it. | May ask for title, then draft (multi-turn) |

## Parity

| # | Action | Expected |
|---|--------|----------|
| 36 | Same question via **Ask** and hold-to-talk | Same `say` text (voice parity) |
| 37 | Record audio → `/api/run` (if enabled in UI) | Transcript + tool activity + summary |

## Regression (issue title follow-up)

1. If anything is broken, open an issue for it.  
2. Call it broken-in-stuff.  
3. **yes**  

Step 2 must **draft** an issue (not `create_issue() missing title`).

## Automated tests

```bash
python test_friday.py
```
