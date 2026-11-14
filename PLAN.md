# Plan

Junction 2026, 13–15.11.2026. Challenges: **Hostinger "Decode the Noise"** (main) and **Context.dev** (second).

Keeper of this file: the presentation + documentation owner. Anyone may edit it; each role keeps its own status block at the bottom. If two edits conflict, the keeper's version wins and the user is told.

"Branch" in this file means an **open decision**, not a git branch. Branches are listed under [Open branches](#open-branches) and referred to as `B1`, `B2`…

## What we build

**Spot the swarm**: a tool that finds groups of accounts that behave like one actor (bot networks, astroturfing, brigading) from what they share and how, rather than from any single post. Lone bots are out of scope. It runs live on Hostinger with a public URL.

It has two parts (team decision 14.11):

1. **The core** (the MVP, due Sat 14.11): an open-source program anyone can download and run on their own computer, with no accounts, subscriptions or language model. Input: a CSV of comments and an optional CSV of profiles, in one standard format for any website. Output: a list of account clusters that are probably coordinated, each with a confidence and its evidence. Design: `docs/core-design.md`. Build plan: `docs/core-plan.md`.
2. **The website** (after the MVP): runs the core on Hostinger by default. A user gives it data, or a link to a site to analyse. Connected accounts or API keys (Hostinger AI Router, Gemini, OpenAI, Anthropic, Context.dev) add optional features: collecting a site's comments, explaining a cluster in plain language, remote processing. "Run locally" links to the install instructions on GitHub. A result produced locally can be uploaded to the website for the connected tools.

The idea: the core is free and open for everyone; partner tech adds value on top and is never required.

What the judges weigh:
- **Hostinger:** strong and honest detection logic, including how false positives are handled. Measured precision and false-positive rate, not a happy-path demo.
- **Context.dev:** a product that reacts to the live web, turning live web data into decisions or actions. Their challenge text gives no scoring criteria: ask their mentors.

## Approach

The core, in short. The full method and the measurements behind it are in `docs/core-design.md`.

1. **Read** the two CSV files. Only `username` and one content column (`text`, `links`, `repost_of` or `parent_id`) are required. Every other column may be missing: the core warns and carries on.
2. **Reduce** each comment to what it can share with a copy: its text, its links, the post it reposts, the comment it answers.
3. **Link** two accounts when they share more of these than chance predicts. Sharing something popular proves little; one shared item never links anyone.
4. **Group** linked accounts. A group of three or more is a cluster.
5. **Confidence:** how much of what the members post is also posted by other members. Clusters under the cut (default 0.2) are not reported.
6. **Evaluation:** precision, recall and false-positive rate on labelled data, per bot family.

Then the website: upload or collect data, run the core, show the clusters with their evidence, and let connected tools explain them.

What we measured on real data before choosing this (Cresci 2017, 6.6 million tweets):
- Bots repeat each other's text in 64–93% of their tweets; humans in 3.5%.
- The copies come hours apart, so the first skeleton's 60-second rule was the wrong signal.
- Real communities also share content, but only about 5% of what they post. That is why confidence is the share that is copied.

False positives we design for, each with a test:
- breaking news (everyone shares one link at once)
- real activist or fan campaigns
- one viral post being reposted
- a common short greeting
- benign automated feeds (news, weather). **Known limit:** these are still flagged. Feeds that post the same wire text are coordinated by our definition.

## Timeline

| When | Block | Done when |
|---|---|---|
| Fri 13.11, until 01:00 | **Setup** | Draft submitted on the Junction Platform. All four in the repo and able to push. VPS answers on a public URL with a hello-world container. AI Router key answers one test call. Context.dev credits redeemed and one test call works. Data owner has two candidate datasets confirmed downloadable. |
| Sat 09:00–10:30 | **Lock the design** | `docs/core-design.md` approved by the team. Hostinger mentors asked whether the two-part idea fits their challenge (B13). Context.dev mentors asked what their API can collect (B11). |
| Sat 10:30–13:00 | **Core, first half** | `docs/core-plan.md` tasks 1–4: CSV in, clusters out, tests pass. The front end builds against the output format in the design. |
| Sat 13:00–13:45 | Lunch + Hostinger keynote | The presentation owner attends; the rest keep building. |
| Sat 13:45–18:00 | **Core MVP done** | Tasks 5–7: command line, numbers on the real dataset recorded below, API on the live URL showing the synthetic sample. |
| Sat 18:00–18:30 | Dinner + **checkpoint** | Scope of the website cut to what can be finished. |
| Sat 18:30–23:00 | **Website (part 2)** | Run the core from the site. Then, in this order, as far as time allows: collect comments from a link (Context.dev), explain a cluster (AI Router), upload a local result. Dashboard usable. |
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
| **Backend** | Arde1001 | The core: CSV input, signals, clustering, confidence, evaluation, command line, API | `backend/`, `docs/api.md`, `docs/core-design.md`, `docs/core-plan.md`, `CLAUDE.md` |
| **Front end + infrastructure** | Makeee22 | Dashboard, Hostinger VPS, domain, Docker, deploys, the live URL | `frontend/`, `deploy/`, `docker-compose.yml` |
| **Presentation + documentation** | J0l3s | Junction submission, deck, video, demo script, README, mentor contact, keeper of this file | `docs/pitch/`, `README.md`, `PLAN.md` |
| **Data + detection criteria** | TheSnowman99 | Datasets, labelled test set, signal definitions and thresholds, reading the false positives | `data/`, `docs/criteria.md` |

## Open branches

Status is `OPEN` or `DECIDED`. When a branch is decided, write the date and the choice, and keep the other options listed.

| ID | Decision | Options | Status / default | Decide by |
|---|---|---|---|---|
| **B1** | Direction | Spot the swarm / Name the technique / Clean the traffic / Trust the source | **DECIDED 13.11: Spot the swarm** | done |
| **B2** | Role of the language model | Judge of rule-found candidates / also finds candidates itself / explanation only / none | **DECIDED 14.11: none in the core; explanation only, on the website**, through a connected account | done |
| **B3** | Stack | Python (FastAPI, pandas, networkx) in Docker / Node.js | **DECIDED 14.11: Python (FastAPI) in Docker** | done |
| **B4** | Front end | Static page served by the backend / separate app / Hostinger AI Builder calling our API | OPEN. The front-end owner decides. Fixed on 14.11: the site runs the core on Hostinger by default, "run locally" links to GitHub, and a local result can be uploaded | Sat 13:00 |
| **B5** | Deploy method | SSH `git pull && docker compose up -d --build` / GitHub Actions / Hostinger MCP | OPEN. Default: SSH one-liner | Fri night |
| **B6** | Git workflow | Everyone on `main` / feature branches with review / owner per directory | **DECIDED 13.11: owner per directory**, see [Git workflow](#git-workflow) | done |
| **B7** | Second challenge | Hostinger only / also Context.dev | **DECIDED 13.11: also Context.dev** | done |
| **B8** | Evaluation data | Labelled research data mixed with ordinary posts / live open stream / real data with simulated swarms injected | **DECIDED 14.11: Cresci 2017** (labelled Twitter bots and humans; research-only licence, so it is never published) **for the numbers, plus synthetic look-alikes for the false-positive tests** | done |
| **B9** | Storage | Files or SQLite / DuckDB / MariaDB with vector search on the VPS | **DECIDED 14.11: DuckDB inside the core**, in a temporary file per run. Nothing is stored between runs yet | done |
| **B10** | Text similarity | Exact match on normalised text / small local embedding model / embeddings from AI Router | **DECIDED 14.11: exact match first; a small local embedding model as an optional layer** (`docs/core-plan.md`, task 8) | done |
| **B11** | What Context.dev feeds us | Scraping the comment section of a site the user links / news search on a topic / monitors with webhooks on chosen sites | OPEN. Direction set 14.11: it turns a link into `comments.csv` for the core. Ask their mentors which sites give usernames with the comments | Sat 10:30 |
| **B12** | Product shape | One hosted tool / open core + website with partner tools | **DECIDED 14.11: open core + website**, see [What we build](#what-we-build) | done |
| **B13** | Does the two-part idea fit Hostinger's challenge? | Yes as is / the core needs AI in it / something else | OPEN. Ask the Hostinger mentors. The challenge text says "AI tool" and the core has no language model | Sat 10:30 |
| **B14** | Lone bots | In scope / out of scope | **DECIDED 14.11: out of scope.** A cluster is at least three accounts | done |

## Partner tech

| Partner | What we get | Use for us |
|---|---|---|
| **Hostinger** | VPS, AI Router credits, AI Builder, MCP | Hosting the website and the core; explaining clusters (AI Router); optionally the front end |
| **Context.dev** | Team credits; search, scrape, crawl, news search, monitors with webhooks, batch API | Collecting a site's comments from a link (B11); second challenge |
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

Record every evaluation run here: date and time, dataset, variant, precision, recall, false-positive rate, and what changed. Counted per account: recall is the share of labelled bots found, false-positive rate the share of labelled humans flagged.

| When | Dataset | Variant | Precision | Recall | False-positive rate | Change |
|---|---|---|---|---|---|---|
| 14.11 00:30 | **Synthetic** sample (216 accounts, 13 in two simulated swarms) | first skeleton (same text within 60 s) | 0.81 | 1.00 | 0.015 | First version. The 3 false positives are the simulated benign news feeds: timing and text reuse cannot tell them from a swarm. Shows the code works, says nothing about real data. |
| 14.11 02:20 | Cresci 2017 (10,159 accounts with content: 1,083 human, 9,076 bot) | **design measurement**, throwaway scripts, not the product code | 1.000 | 0.73 | 0.000 | The method in `docs/core-design.md`. Bots found per family: social 1 95%, social 2 100%, social 3 95%, traditional 47%, fake followers 41%. Without the confidence cut: precision 0.978, 14.1% of humans flagged. **The cut 0.2 was chosen with these labels visible, so this row is optimistic.** These bots copy text word for word; a swarm that rewords would do worse. |
| 14.11 10:35 | Cresci 2017 (10,159 labelled accounts with content: 1,083 human, 9,076 bot; 6,637,615 comments) | **core, rules only** (product code, `python -m swarm`) | 1.000 | 0.726 | 0.000 | First run of the real core, 49 s on the laptop. Bots flagged per family: social 1 95.3%, social 2 99.5%, social 3 94.6%, traditional 46.9%, fake followers 41.0%. Without the confidence cut: precision 0.978, 14.1% of humans flagged; at 0.05: precision 0.9994, 0.4% of humans. Matches the design measurement. **The cut 0.2 was chosen with these labels visible.** |
| 14.11 11:20 | **Synthetic** sample with an extra reworded swarm (262 accounts, 19 bots in three simulated swarms; 5,869 comments) | core, rules only | 0.8125 | 0.684 | 0.0123 | The reworded swarm (6 accounts, every member words each message differently) is missed. Same data without the layer. |
| 14.11 11:20 | **Synthetic**, same as above | core + similar-text layer (`--similar-text`, cosine 0.9, `potion-base-8M`) | 0.864 | 1.000 | 0.0123 | The reworded swarm is found, at confidence 0.252: just above the 0.2 cut. Nearest-neighbour cosine between its variants: min 0.876, median 0.94, so some variants fall below 0.9; the swarm is found through the others. The two real swarms' confidence drops a little (0.375 to 0.371 and 0.323). Says the code works, not how good the layer is on real text. |
| 14.11 11:30 | Cresci 2017, **300 genuine accounts only** (first 300 by sorted username among those with comments; up to 500 comments each, 148,288 comments, 82,572 distinct texts) | core, rules only | n/a | n/a | 0 of 300 flagged | 0 clusters. Humans only, so this measures false positives and nothing else. Run time 2 s. |
| 14.11 11:30 | Same 300 genuine accounts | core + similar-text layer | n/a | n/a | 0 of 300 flagged | 0 clusters. 926 similar-text items, 0 links (after the review fixes; 936 before). Dropping the rule that ignored groups of word-for-word copies, to favour recall, changed nothing here or on the synthetic sample (940 items), so no row of its own. Run time 42 s. The only real-data evidence for the layer: no false positives, but also nothing to find, since humans only. Benefit on real reworded swarms is not measured. |
| 14.11 12:00 | Cresci 2017, **simulated conversation**: window from 2014-10-01, each account's first N comments in it (484–747 human, 1,287–1,454 social-bot accounts) | core, rules only (`65e1ed1`) | 0.84–0.93 where anything is found | **0.000–0.026** for N ≤ 20; 0.280 (7 days, all), 0.421 (30 days, all) | 0.000–0.015 | **Test A** (`docs/test-a-conversation.md`): with the few comments per account of one conversation the core finds almost no bots, and it fails safe (flags almost nobody). Recall needs long histories. The product goal "check your comment section" needs the participants' histories, not just the thread. |

## Status by role

Each role keeps its own block.

### Backend
- Done: research, measurements on Cresci 2017, the core design (`docs/core-design.md`) and build plan (`docs/core-plan.md`). The core on branch `arde/core`: CSV loading, detection, metrics, result document, synthetic data, Cresci converter, command line (`python -m swarm`), and the read-only API on the new result. The contract is rewritten in `docs/api.md`.
- Doing: the real-data numbers (Results table) and merging `arde/core` to `main` once the plan's task 7 is green.
- Blocked: nothing.
- For everyone: please read `docs/core-design.md`, at least "Input format", "Output" and "Known limits".
- For Makeee22: build against `docs/api.md` (new fields; `verdict` is gone, `confidence` replaces it; paths and port 8000 are unchanged). The image still listens on port 8000 and has not been built locally (no Docker on the backend owner's machine), so please build it first. It needs `requirements.txt` (now with `duckdb`) and `swarm/` only. The API shows one result, chosen by environment variables: `RESULT_FILE` (a JSON file from `python -m swarm ... --out`), else `COMMENTS_FILE` and optionally `PROFILES_FILE` (analysed at startup), else the synthetic sample. If a variable points to a bad file, the container exits with one message line, so check the container log. Mount the data file as a volume; never bake data into the image.
- For TheSnowman99: the parameters to tune are in the design under "Parameters". Cresci 2017 is on Arde1001's machine only; `data/README.md` should say where it comes from (http://mib.projects.iit.cnr.it) and that its licence allows research use only.

### Front end + infrastructure
- Done (branch `makeee22/frontend`): **live at https://swarm.srv2159299.hstgr.cloud** (VPS behind Hostinger's Traefik, Let's Encrypt HTTPS; `deploy/README.md`). Dashboard in `frontend/site/` on the new `docs/api.md`: upload of comments + optional profiles CSV, confidence, signals and warnings, evidence per swarm, metrics at every cut with the "cut chosen with labels visible" note, synthetic badge. `frontend/api/` = the backend's `swarm.api` unchanged + `POST /api/analyze` running `swarm.core.analyze()`.
- B4 choice: **static page**, no build step, served by nginx, which also proxies `/api/` to the API container. The table above still says OPEN: for the keeper to mark.
- Doing: merging `makeee22/frontend` to `main`.
- For Arde1001: the numpy start-up crash is fixed in `a0893fd`/`54664a6` (tested on the VPS); the stopgap in `frontend/api/` is gone. When the backend has its own upload endpoint, `frontend/api/` can go (`deploy/docker-compose.backend.yml`).
- Blocked: nothing.

### Presentation + documentation
- Done:
- Doing:
- Blocked:

### Data + detection criteria
- Done:
- Doing:
- Blocked:
