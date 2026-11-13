# Plan

Junction 2026, 13–15.11.2026. Challenges: **Hostinger "Decode the Noise"** (main) and **Context.dev** (second).

Keeper of this file: the presentation + documentation owner. Everyone else edits only their own status block at the bottom, or asks the keeper.

"Branch" in this file means an **open decision**, not a git branch. Branches are listed under [Open branches](#open-branches) and referred to as `B1`, `B2`…

## What we build

**Spot the swarm**: a tool that detects coordinated inauthentic behaviour (bot networks, astroturfing, brigading) from posting timing, account similarity, text reuse and amplification patterns, rather than from any single post. It takes in live web content through Context.dev, and runs live on Hostinger with a public URL.

What the judges weigh:
- **Hostinger:** strong and honest detection logic, including how false positives are handled. Measured precision and false-positive rate, not a happy-path demo.
- **Context.dev:** a product that reacts to the live web, turning live web data into decisions or actions. Their challenge text gives no scoring criteria: ask their mentors.

## Approach

A proposal. The undecided parts are branches.

1. **Ingest** posts: account, timestamp, text, links, hashtags, repost-of. Sources: a labelled dataset for evaluation (B8), and live web content through Context.dev (B11).
2. **Signals** between accounts: near-identical text, the same link or hashtag posted within a short window, repeated co-activity over time, account similarity (creation-date bursts, name patterns).
3. **Graph:** accounts are nodes, repeated co-actions are weighted edges. Dense groups become candidate swarms.
4. **Score** each candidate and collect its evidence.
5. **Decision model** (a language model through Hostinger AI Router): receives one candidate's evidence and sample posts. Returns a verdict (coordinated / probably organic / unclear), a confidence, reasons in plain language, and the innocent explanations it ruled out.
6. **Evaluation:** precision, recall and false-positive rate on labelled data, reported for rules alone and for rules + decision model.
7. **Dashboard:** a list of swarms, each with its timeline, account graph, evidence and verdict.

False positives to design for from the start:
- breaking news (everyone shares one link at once)
- real activist or fan campaigns
- benign automated feeds (news, weather)
- one viral post being reposted

## Timeline

| When | Block | Done when |
|---|---|---|
| Fri 13.11, until 01:00 | **Setup** | Draft submitted on the Junction Platform. All four in the repo and able to push. VPS answers on a public URL with a hello-world container. AI Router key answers one test call. Context.dev credits redeemed and one test call works. Data owner has two candidate datasets confirmed downloadable. |
| Sat 09:00–10:30 | **Lock the design** | B2, B3, B8, B11 decided. API contract written in `docs/api.md`. Mentor check at the Hostinger and Context.dev booths. |
| Sat 10:30–13:00 | **Walking skeleton** | Data in, a (dumb) swarm list out, shown on the live URL. The front end runs against mock JSON until then. |
| Sat 13:00–13:45 | Lunch + Hostinger keynote | The presentation owner attends; the rest keep building. |
| Sat 13:45–18:00 | **Core detection** | Real signals and clustering. The evaluation script prints precision, recall and false-positive rate. First numbers recorded below. |
| Sat 18:00–18:30 | Dinner + **checkpoint** | Scope cut to what can be finished. |
| Sat 18:30–23:00 | **Decision model and explanations** | Verdicts with reasons. False-positive cases handled. Live Context.dev feed connected. Dashboard usable. Numbers for both variants. |
| Sat 23:00 | **Feature freeze** | Bug fixes only. |
| Sat 23:00–02:00 | **Package** | Deck draft, video script, README, demo script. |
| Sun 02:00–06:00 | Sleep | |
| Sun 06:30–08:30 | **Record and finish** | Video under 2:00 and public. Deck as PDF. Live URL tested from a phone on mobile data. |
| Sun 08:30 | **Submit as FINAL** | For both challenges. Editable until 10:00. |
| Sun 09:30 | **Hands off** | No more deploys. |
| Sun 10:00 | Hard deadline | |
| Sun 10:30–14:00 | Peer review | All four at the table. |

## Roles

| Role | Person | Owns | Directories |
|---|---|---|---|
| **Backend** | Arde1001 | Ingest, signals, clustering, decision model, evaluation script, API | `backend/`, `docs/api.md`, `CLAUDE.md` |
| **Front end + infrastructure** | Makeee22 | Dashboard, Hostinger VPS, domain, Docker, deploys, the live URL | `frontend/`, `deploy/`, `docker-compose.yml` |
| **Presentation + documentation** | J0l3s | Junction submission, deck, video, demo script, README, mentor contact, keeper of this file | `docs/pitch/`, `README.md`, `PLAN.md` |
| **Data + detection criteria** | TheSnowman99 | Datasets, labelled test set, signal definitions and thresholds, the rubric the decision model follows, reading the false positives | `data/`, `docs/criteria.md` |

## Open branches

Status is `OPEN` or `DECIDED`. When a branch is decided, write the date and the choice, and keep the other options listed.

| ID | Decision | Options | Status / default | Decide by |
|---|---|---|---|---|
| **B1** | Direction | Spot the swarm / Name the technique / Clean the traffic / Trust the source | **DECIDED 13.11: Spot the swarm** | done |
| **B2** | Role of the decision model | Judge of rule-found candidates / also finds candidates itself / explanation only | OPEN. Default: judge of candidates | Sat 10:30 |
| **B3** | Stack | Python (FastAPI, pandas, networkx) in Docker / Node.js | **DECIDED 14.11: Python (FastAPI) in Docker** | done |
| **B4** | Front end | Static page served by the backend / separate app / Hostinger AI Builder calling our API | OPEN. The front-end owner decides | Sat 13:00 |
| **B5** | Deploy method | SSH `git pull && docker compose up -d --build` / GitHub Actions / Hostinger MCP | OPEN. Default: SSH one-liner | Fri night |
| **B6** | Git workflow | Everyone on `main` / feature branches with review / owner per directory | **DECIDED 13.11: owner per directory**, see [Git workflow](#git-workflow) | done |
| **B7** | Second challenge | Hostinger only / also Context.dev | **DECIDED 13.11: also Context.dev** | done |
| **B8** | Evaluation data | Labelled research data mixed with ordinary posts / live open stream / real data with simulated swarms injected | OPEN. Default: a labelled set for the numbers + injected swarms for a controlled test | Sat 10:30 |
| **B9** | Storage | Files or SQLite / MariaDB with vector search on the VPS | OPEN. Default: files or SQLite | when needed |
| **B10** | Text similarity | Normalised-text hashing / embeddings from AI Router | OPEN. Default: hashing first | Sat 13:00 |
| **B11** | What Context.dev feeds us | News search on a topic / scraping comment sections or forums / monitors with webhooks on chosen sites / copied articles across domains | OPEN. Needs a mentor talk: which source gives accounts and timestamps | Sat 10:30 |

## Partner tech

| Partner | What we get | Use for us |
|---|---|---|
| **Hostinger** | VPS, AI Router credits, AI Builder, MCP | Hosting, the decision model, optionally the front end |
| **Context.dev** | Team credits; search, scrape, crawl, news search, monitors with webhooks, batch API | The live web feed (B11); second challenge |
| **Exa** | Credits per person; meaning-based search, find-similar pages | Optional: tracing one narrative or copied text across sites |
| **MariaDB** | Open-source database with vector search | Optional: similarity search if the data outgrows memory (B9) |
| **Verda / Modal** | GPU compute | Only if we train or embed at scale; not planned |
| **Junction Platform** | Partner credits for other partners' models, under *Developer Tools and Assets* | Not checked yet: someone opens that page and lists what is there |

The promo codes are in the challenge texts, not in this repo.

## Git workflow

**One owner per directory.** Conflicts come from two people editing the same file, so every directory and shared file has exactly one owner (see [Roles](#roles)). Need a change in someone else's area? Ask them.

- **Coders:** work on `main` inside your own directories. Commit small and often. Always `git pull --rebase` before `git push`. Set it once per clone: `git config pull.rebase true`.
- **Risky or cross-cutting work** (anything that could break the live site, or touches another owner's files): a short branch `name/topic`, merged the same day.
- **Non-coders:** edit in the GitHub web editor, in `docs/`, `data/` and this file. No local git needed.
- **The front end and the backend meet only at `docs/api.md`.** The backend owner changes it and tells the front-end owner. The front end builds against mock JSON until the real endpoint exists.
- **Never:** force-push, `git add -A`, commit `.env`, or commit files over about 50 MB. Raw datasets stay in `data/raw/` (ignored); `data/README.md` says where they come from.

## Results

Record every evaluation run here: date and time, dataset, variant (rules / rules + decision model), precision, recall, false-positive rate, and what changed.

| When | Dataset | Variant | Precision | Recall | False-positive rate | Change |
|---|---|---|---|---|---|---|
| 14.11 00:30 | **Synthetic** sample (216 accounts, 13 in two simulated swarms) | rules | 0.81 | 1.00 | 0.015 | First version. The 3 false positives are the simulated benign news feeds: timing and text reuse cannot tell them from a swarm. Shows the code works, says nothing about real data. |

## Status by role

Each role edits only its own block.

### Backend
- Done: walking skeleton in `backend/`: text-reuse + timing detection, account-level evaluation, read-only API (`docs/api.md`), synthetic test data, `backend/Dockerfile`.
- Doing: waiting for B2, B8, B11 before the decision model and the live feed.
- Blocked: needs the AI Router and Context.dev keys; needs a first real dataset in the format of `docs/api.md` ("Input data format").
- For Makeee22: the backend container listens on port 8000 (`backend/Dockerfile`); `docker-compose.yml` is yours. The Docker image is not built or tested yet.
- For TheSnowman99: the thresholds to tune are the four constants at the top of `backend/swarm/detect.py`.

### Front end + infrastructure
- Done:
- Doing:
- Blocked:

### Presentation + documentation
- Done:
- Doing:
- Blocked:

### Data + detection criteria
- Done:
- Doing:
- Blocked:
