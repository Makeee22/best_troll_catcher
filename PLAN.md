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
3. **Link** two accounts when they share more of these than chance predicts. Sharing something popular proves little; one shared item links nobody, unless it is a long text (10 words or more) that still beats chance.
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
| **Backend + collection** | Arde1001 | The core (CSV input, signals, clustering, confidence, evaluation, command line, API) and, since 14.11 evening, the whole path from a URL to the result: collect, convert, analyse | `backend/`, `docs/api.md`, `docs/collect-interface.md`, `docs/core-design.md`, `docs/core-plan.md`, `CLAUDE.md` |
| **Front end + infrastructure** | Makeee22 | Dashboard and everything done with the returned result (including the language-model explanation), Hostinger VPS, domain, Docker, deploys, the live URL | `frontend/`, `deploy/`, `docker-compose.yml` |
| **Presentation + documentation** | J0l3s | Junction submission, deck, video, demo script, README, mentor contact, keeper of this file | `docs/pitch/`, `README.md`, `PLAN.md` |
| **Data + detection criteria** | TheSnowman99 | Datasets, labelled test set, signal definitions and thresholds, reading the false positives | `data/`, `docs/criteria.md` |

## Open branches

Status is `OPEN` or `DECIDED`. When a branch is decided, write the date and the choice, and keep the other options listed.

| ID | Decision | Options | Status / default | Decide by |
|---|---|---|---|---|
| **B1** | Direction | Spot the swarm / Name the technique / Clean the traffic / Trust the source | **DECIDED 13.11: Spot the swarm** | done |
| **B2** | Role of the language model | Judge of rule-found candidates / also finds candidates itself / explanation only / none | **DECIDED 14.11: none in the core; explanation only, on the website**, through a connected account | done |
| **B3** | Stack | Python (FastAPI, pandas, networkx) in Docker / Node.js | **DECIDED 14.11: Python (FastAPI) in Docker** | done |
| **B4** | Front end | Static page served by the backend / separate app / Hostinger AI Builder calling our API | **DECIDED 14.11 (front-end owner): static page**, no build step, served by nginx, which proxies `/api/` to the API container (Makeee22's status block). Also fixed on 14.11: the site runs the core on Hostinger by default, "run locally" links to GitHub, and a local result can be uploaded | done |
| **B5** | Deploy method | SSH `git pull && docker compose up -d --build` / GitHub Actions / Hostinger MCP | **DECIDED: SSH one-liner** (`git pull && docker compose … up -d --build`, `deploy/README.md`) | done |
| **B6** | Git workflow | Everyone on `main` / feature branches with review / owner per directory | **DECIDED 13.11: owner per directory**, see [Git workflow](#git-workflow) | done |
| **B7** | Second challenge | Hostinger only / also Context.dev | **DECIDED 13.11: also Context.dev** | done |
| **B8** | Evaluation data | Labelled research data mixed with ordinary posts / live open stream / real data with simulated swarms injected | **DECIDED 14.11: Cresci 2017** (labelled Twitter bots and humans; research-only licence, so it is never published) **for the numbers, plus synthetic look-alikes for the false-positive tests** | done |
| **B9** | Storage | Files or SQLite / DuckDB / MariaDB with vector search on the VPS | **DECIDED 14.11: DuckDB inside the core**, in a temporary file per run. Nothing is stored between runs yet | done |
| **B10** | Text similarity | Exact match on normalised text / small local embedding model / embeddings from AI Router | **DECIDED 14.11: exact match first; a small local embedding model as an optional layer** (`docs/core-plan.md`, task 8) | done |
| **B11** | What Context.dev feeds us | Scraping the comment section of a site the user links / news search on a topic / monitors with webhooks on chosen sites | OPEN. Direction set 14.11: it turns a link into `comments.csv` for the core. Ask their mentors which sites give usernames with the comments. **Decided 14.11 afternoon: besides the thread, scrape each commenter's last ~15 comments** (full histories cost too much); **the site uses 25 for Reddit and 30 for Bluesky** (14.11 evening). Measured on Cresci with the long-text rule: 10 comments per account picked across each history gives recall 0.778, full histories 0.790, 3 comments 0.350 (tweets, not comment sections); Test A after the unbiased chance rate (14.11 evening): 0.85–0.94 at 10 comments per account inside one window, about 0.36 at 20, so in bot-heavy windows fewer history comments find more; whether 25–30 should drop towards 10 is not settled yet. Later saving: fetch histories only for accounts that already share something in the thread | Sat 10:30 |
| **B12** | Product shape | One hosted tool / open core + website with partner tools | **DECIDED 14.11: open core + website**, see [What we build](#what-we-build) | done |
| **B13** | Does the two-part idea fit Hostinger's challenge? | Yes as is / the core needs AI in it / something else | **DECIDED 14.11 afternoon (mentors not reached): continue as planned.** No language model in the core; its only model is the embedding model that recognises reworded copies with the same meaning (statistics do the rest). A larger cloud embedding model through a partner API only if it raises recall clearly. Language-model explanations stay a website extra | done |
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
| 14.11 13:00 | Same simulated conversation as Test A | core, rules only, **after the long-text rule** (`73def06`) | 1.000 at 3–5 per account; 0.84–0.93 at 10 | **0.28–0.32** at 3 per account, **0.65–0.73** at 5; **0.000–0.026** at 10 and 20 | 0.000 at 3–5; ≤ 0.013 at 10–20 | **Test A rerun** (`docs/test-a-conversation.md`): the long-text rule works for conversation-sized samples. With more comments per account in the same window recall falls back to near 0: the chance test passes 1,606 text pairs at 5 per account, 118 at 10, 64 at 20, so a 538-account botnet disappears ("Big swarms hide small evidence", now measured). Differs from the thinned-by-hash row above because a window makes the botnet's copies overlap. |
| 14.11 14:00 | Cresci 2017, full (6,637,615 comments, 10,159 labelled accounts with content) | core, rules only (`73def06`) | 1.000 | 0.790 | 0.000 | Rerun of the full set on the current core (0.726 before the long-text rule). |
| 14.11 14:00 | **Cresci subset** `AllComments_Combined.csv` (3,574,246 comments; 4,528 social bots, **377 humans**) | core, rules only (`73def06`) | 0.944 | 0.989 | **0.706** | 266 of 377 humans flagged at every cut, although the same humans are never flagged on the full set. A human community (1,442 repost and 5,378 reply links among themselves) is merged into a 727-bot cluster by 52 human–bot links and inherits its confidence. Flagging members by their own copied share ≥ 0.5 gives FPR 0.101 at recall 0.981 (cut chosen with labels visible). `docs/findings-context-dev-and-subset.md`. |
| 14.11 afternoon | Cresci 2017, full (as above) | core + URL normalisation for links | 1.000 | 0.726 | 0.000 | Links are compared without scheme, `www.`, tracking parameters, fragment and trailing slash. No measurable change here (link items 915,889 to 915,617). |
| 14.11 afternoon | Cresci 2017, full | core + **long-text rule** (one shared text of 10 words or more links a pair if it beats chance) | 1.000 | 0.790 | 0.000 | Recall 0.726 to 0.790, still 0 of 1,083 humans. Per family: fake followers 41.0% to 57.2%, traditional 46.9% to 53.8%, the social families unchanged. Without the cut: precision 0.979, 14.1% of humans. The 10 was fixed before measuring; simulated at 8 words recall is 0.805 and at 15 words 0.768, both with 0 humans. The largest cluster grows to 5,625 accounts (several botnets chained together). **The cut 0.2 was chosen with these labels visible.** |
| 14.11 afternoon | Cresci 2017 **thinned to 10 comments per account** (95,622 comments; comments picked by hash) | before / after the long-text rule | 1.000 / 1.000 | 0.118 / 0.778 | 0.000 / 0.000 | The shape of a scraped comment section: few comments per account. Before the rule the core found almost nothing here. |
| 14.11 afternoon | Cresci 2017 **thinned to 3 comments per account** (29,690 comments) | before / after the long-text rule | 1.000 / 1.000 | 0.018 / 0.350 | 0.000 / 0.000 | Same, thinner still. |
| 14.11 afternoon | **Simulated** swarms planted into the 1,083 genuine Cresci accounts (`python -m swarm.inject`, 20 scenarios), core before the long-text rule | n/a | see Change | 0 of 1,083 in every run | Found in full: 3 to 50 accounts copying 6 messages with 10 own posts each; 3 or 20 copied messages. Missed: 1 or 2 copied messages, 30 or more own posts per member (confidence falls under 0.2), edited copies, reworded copies. Half or a quarter of the members posting each message: 6 of 8 and 3 of 8 found. |
| 14.11 evening | Same **simulated** swarms, core with the long-text rule | n/a | see Change | 0 of 1,083 in every run | Newly found: a swarm of 8 that pastes one 15-word message, when its members post 0 or 2 other comments (8 of 8; before 0 of 8); half of the members posting each message (8 of 8; before 6 of 8). Still missed: one 7-word message; 1 or 2 copied messages among 10 own posts (confidence under 0.2); 30 or more own posts per member; edited and reworded copies. |
| 14.11 evening | Cresci 2017 full and thinned; simulated edited swarms | **tried, not adopted**: a model-free near-duplicate signal (word overlap of at least 0.7, MinHash) | | | | Full data: skipped by its own limit (over 20 million candidate text pairs). Thinned to 10 comments: recall fell from 0.778 to 0.129, because its many weak pairs make the shared chance test stricter and the long-text links no longer pass. Planted edited swarms: 0 of 8 found. The code is kept on the local branch `worktree-agent-ab2baf9926f379590` only. It shows a limit that also applies to `--similar-text`: all signals share one chance test, so a noisy signal can hide the others. |
| 14.11 afternoon | Cresci 2017, full | **tried, not adopted** (simulated on the product's tables) | | | | (1) Reporting a cluster also through its share of copied text: recall +0.010 for 4 humans flagged (four accounts that share 66 long texts), and it makes the cut meaningless for text-only data. (2) Splitting clusters by label propagation: recall 0.726 to 0.714, and the largest cluster still mixes families. |
| 14.11 evening | Test A windows (rebuilt from `docs/test-a-conversation.md`), Cresci full, thinned and humans only; planted swarms in 300 genuine accounts | core + **unbiased chance of a match** (`S` counts pairs of different posts; before, each post also matched itself) | 1.000 on Cresci full | Test A, 10 per account: 1 day 0.000 to **0.848**, 7 days 0.026 to **0.940**, 30 days 0.025 to **0.926**; 20 per account: 7 and 30 days 0.000 to **0.358** / **0.352**, 1 day still 0.000; 3, 5, 50 and all unchanged. Cresci full 0.790 to 0.791, thinned to 10: 0.778 to 0.787 | Cresci full and humans only: 0 of 1,083. Test A: humans flagged 3 to 5 (7 days, 10 per account), 7 to 8 (30 days, 10), 10 to 11 (30 days, 20), otherwise unchanged | Recall still **falls** with more comments per account in a window (0.94 at 10, 0.36 at 20, 0.50 at 50, 0.28 for the whole week). Nearly every shared text in these windows is bot–bot (31,446 of 31,493 pairs at 20 per account), so the swarm sets the chance rate it is tested against. Test A has about two bots per human, the worst case for any rate taken from the data. Planted swarms: same as before, half-participation 6 to 8 of 8, 0 background accounts flagged. |
| 14.11 evening | Same as above | **tried, not adopted**: estimate the chance rate again without the accounts already found (up to 5 passes, optional loose first pass) | | Test A 50 per account and whole windows: up to 0.95 | **Cresci full: 879 of 1,083 humans flagged**; 30 days whole window: 52 humans | Once the bots are out, the rate comes from humans alone, who almost never copy, so any two humans sharing one long text link. Would need a fixed floor on the rate, which is a new parameter chosen with labels in view. |
| 14.11 15:30 | **Synthetic** reworded sample; planted swarms in 300 genuine Cresci accounts (`swarm.inject --similar-text`); a **simulated** Finnish reworded swarm of 8 planted in the same 300 | `--similar-text` with the **multilingual model** `potion-multilingual-128M` (new default) against the English `potion-base-8M`, cut 0.9 for both | Synthetic 0.864 with either | Synthetic 1.000 with either (reworded swarm at 0.221, English 0.252). Planted: the same swarms found with both, multilingual confidence equal or higher (e.g. reworded 0.276 vs 0.260, 50 accounts 0.440 vs 0.378). Finnish swarm: 8 of 8 with both, 0 without the layer | 0 background accounts flagged with either; synthetic humans 0 | Among 20,000 distinct background texts, pairs at cosine 0.9 or more: multilingual 293, English 3,087. Hand-written Finnish: unrelated pairs at most 0.43 (multilingual) vs 0.73 (English). Three Finnish synonym rewordings: 0.79–0.85 with the multilingual model (under the cut), 0.88–0.95 with the English one (two over), which rewards shared letters. **Tried, not adopted:** a cut of 0.8 for the multilingual model chains the synthetic texts into one group of over 200, which is left out, so the synthetic reworded swarm was lost. Cost: 512 MB download, about 1.9 GB of memory, 4 s to load (English: 30 MB, 150 MB). Simulated data in the Finnish and planted rows. |
| 14.11 15:30 | Synthetic sample; Cresci 2017 full | `declared_automation` mark on each cluster (members that call themselves a bot, feed or RSS in their name or bio) | unchanged | unchanged (Cresci full 0.791) | unchanged (0 of 1,083) | Additive only: same clusters and confidence, checked by a test with a swarm posing as a feed. Synthetic: the 3 feeds are marked, both swarms are not. Cresci: 0 of 21 clusters marked, because our conversion keeps no names or bios, so the mark cannot be measured on real bots. Why not posting style: Cresci bots reply in 5% and mention someone in 9.5% of their posts (humans 26% and 61%), so a "broadcasts" rule would mark bot swarms as feeds. |
| 14.11 17:00 | Synthetic reworded sample; planted swarms in 300 genuine Cresci accounts (`--similar-text`, both models); **simulated** Finnish swarm in the same 300; Test A 7 d at 10 and 20 per account, 30 d at 10 and 50; Cresci thinned to 3 | `--similar-text` chance rate over **all** texts (before: only texts with a near-duplicate, so on clean data the swarm set its own rate) | unchanged | Synthetic, planted and Finnish: identical to the 15:30 row. Test A 30 d, 50 per account: 0.721 to **0.746** (English model); other sets unchanged | unchanged in every set (planted: 0 background accounts; Test A: same humans flagged) | A reworded swarm in otherwise clean data (3 accounts, 3 reworded messages, 40 background accounts) is now found; before, nothing was (new test). Similar-text links on Test A 30 d / 50: 138 to 276. |
| 14.11 16:00 | Cresci 2017 **simulated conversation** (Test A cuts) | core rules only, after the unbiased chance rate (`b267a68`/`f14718f`) | 0.994–1.000 at 10 per account | **0.848–0.940 at 10** (was 0.000–0.026); 0.352–0.358 at 20; 0.28–0.32 at 3; 0.65–0.73 at 5 | 0.000–0.015 | Test A rerun (`docs/handoff-frontend-to-backend.md` 1a). The fix works at 10 comments per account; at 20 a large active botnet still hides (social 1 at 12%). |
| 14.11 16:30 | **Real Reddit background** (26 commenters of one r/worldnews thread, 25 newest comments each, via Context.dev) + planted **simulated** swarms (`swarm.inject`, core `c759a49`) | rules / `--similar-text` | n/a | copying swarms of 3–20 accounts 100%; 50 accounts 0/50; ≥30 own posts 0/8; edited and reworded 0/8 rules, **8/8 with similar-text** | **0 real accounts flagged in all 20 scenarios** | `docs/handoff-frontend-to-backend.md` 1b. |
| 14.11 19:00 | **Test R: community-reported Reddit bots, May–November 2026** (296 accounts named in 29 report posts; 72 still had usable comments, in 16 reported networks; background: 96 commenters from 16 threads the reported accounts commented in; newest 25 comments each, 4,053 comments) | core, rules only / + similar-text layer (`1b0866f`) | 0.909 / 0.909 (10 of 11) | 0.139 / 0.139 (10 of 72) | 0.010 / 0.010 (1 of 96) | First test on present-day bots (`docs/test-r-reported-bots.md`). Two clusters (4 and 7 accounts, confidence 0.69 and 0.64), all links are word-for-word short phrases, both from one reported network (10 of its 30 found, split in two). The other 15 networks share no comment text among co-reported accounts in 25 comments, so nothing can link them: they post images or links, write each comment differently, or are single accounts. The one background account flagged was created in the same 30 days as its cluster and shares 2–4 phrases with it: probably an unreported bot. Similar-text: 22 items, 0 links. 57% of the reported accounts were already gone or unreadable. **Weak labels** (user reports, extracted by pattern), background not verified as human, small numbers. |
| 14.11 evening | Cresci 2017 full, humans only, thinned to 10 and 3; Test A 1 d, 7 d and 30 d at 10, 20, 50 per account | core + **created together**: two accounts created within 30 days of each other count one more shared item on top of shared content, tested both ways and the stronger counted at twice the p-value (branch `arde/detect-fixes`) | unchanged in every set (Cresci full 1.000) | unchanged in every set (Cresci full 0.791, thinned 10 0.787, Test A 7 d at 10 0.940) | unchanged (0 of 1,083 humans) | Aimed at Test R's phrase-pasting network made in one batch (`docs/test-r-reported-bots.md`), whose data is not on this machine: Makeee22 to rerun Test R. **Tried first, not adopted:** adding the creation chance to every dated pair weakened strong text pairs, because bots made in bursts make that chance large: Test A 7 d at 10 0.940 to 0.000, Cresci thinned to 10 0.787 to 0.027. Planted swarms have no creation dates, so `swarm.inject` cannot show it. |
| 14.11 evening | Same sets; planted swarms in the 1,083 genuine Cresci accounts (`swarm.inject`, 20 scenarios) | core + **member-level flags**: a member counts as flagged when its copied share is at least half its cluster's confidence (`member_ratio` 0.5: the value was not tuned, the form of the rule was revised once after a labelled run, see "Tried first") | Test A 30 d at 20: 0.979 to 0.985; 7 d at 10: 0.996 to 0.997 | Cresci full 0.791 to **0.766**, thinned 10 0.787 to 0.714, thinned 3 0.350 to 0.341; Test A 1 d at 10 0.848 to 0.758, 7 d at 10 0.940 to 0.910, 30 d at 10 0.926 to 0.896, at 20 about −0.003 | Test A humans flagged 5 to 4, 8 to 6, 11 to 8; Cresci 0 of 1,083 unchanged. Planted: 0 background accounts in all 20 | Against the Cresci subset trap (266 of 377 humans flagged through 52 bridging links; their share 0.32, the cluster's 0.79), which is on Makeee22's machine: **to be rerun there**. Planted: every scenario as before except half participation, 8 to **6 of 8** (the two lightest copiers are linked, not flagged). **Tried first, not adopted:** a fixed member cut of 0.5 flags no member of a swarm that also posts its own comments (synthetic: 6 copies in 16 posts = 0.375) and cut Test A 7 d at 10 to 0.622 and Cresci thinned 10 to 0.321. |
| 14.11 21:20 | **Cresci subset** `AllComments_Combined.csv` (3,574,246 comments; 4,528 social bots, 377 humans) | core + member-level flags, rules only (`002022e`) | 0.977 | 0.982 | **0.281** | 106 of 377 humans flagged (was 266, FPR 0.706). Clusters: 1,056 accounts of which 829 flagged, 303 of 303, 3,440 of which 3,422; the same at every cut 0–0.5. The relative member rule removes 160 of the 266 bridged humans; the fixed own-share cut 0.5 measured earlier gave 0.101 (not adopted, see the row above). Run on Makeee22's machine, aggregate numbers only. |
| 14.11 evening | 80,000 and 400,000 distinct Cresci texts | `--similar-text` by **random-projection hashing** above 50,000 distinct texts (limit raised from 100,000 to 1,000,000) | n/a | 99.8% of the exact near-duplicate pairs found at 80,000 texts, 0 wrong ones (each candidate is checked at cosine 0.9) | n/a | Speed: 80,000 texts 24 s exact vs 8 s hashed; 400,000 texts 50 s hashed (about 4 min exact). Up to 50,000 texts the exact comparison is kept, so every earlier result stands. |

## Status by role

Each role keeps its own block.

### Backend
- Done: the core (CSV loading, detection, metrics, result document, synthetic data, Cresci converter, command line, read-only API), the injection benchmark (`python -m swarm.inject`), the long-text rule, URL normalisation for links, `--ignore FILE`, `copy_gap_seconds` as evidence, and (14.11 afternoon) the unbiased chance rate, the multilingual similar-text model and the `declared_automation` mark. All on `main`; numbers in Results. (14.11 evening) The converter `python -m swarm.convert` for Reddit: a saved thread page plus Context.dev `reddit-user` histories go to the two CSV files (`docs/collect-interface.md`). Then (14.11, later) Context.dev's review and comment parsers, Bluesky and Hacker News, and the schema.org reader. All on `main` (`bac6acd`).
- Tried and not adopted, with numbers in Results: a second reporting route through copied text, splitting clusters by label propagation, a model-free near-duplicate signal.
- Open: **chaining**: on the Cresci subset (377 humans next to 4,528 social bots) 266 humans are flagged, because 52 human–bot links merge a human community into a botnet's cluster and its members inherit the cluster's confidence (`docs/findings-context-dev-and-subset.md`); member-level flags (on `main`) bring it from 266 to 106 (FPR 0.706 to 0.281, rerun 14.11 21:20). **History length**: recall in a bot-heavy conversation window falls from 0.85–0.94 at 10 comments per account to about 0.36 at 20 (Test A), while the site fetches 25 (Reddit) and 30 (Bluesky) per participant. Finnish synonym rewordings score under the similar-text cut; Chinese and Japanese text gives no text item (no spaces). All signals share one chance test, so a noisy signal can hide the others (testing each signal on its own is the next thing to measure). A swarm whose members post 30 or more own comments per 6 copied ones is missed at the default cut; `--min-confidence 0.05` finds it, at the cost of 4 of 1,083 genuine accounts. The largest Cresci cluster chains several botnets together (5,625 accounts).
- Blocked: nothing.
- Done and on `main` (14.11 evening, `bac6acd`): member-level flags against chaining, the created-together item, similar-text by hashing up to 1,000,000 texts, `model2vec` in the requirements and the model in the image (numbers in Results); the schema.org reader for the converter; and the collector:
- Done (14.11 evening): the collector `python -m swarm.collect URL OUT_DIR`: Bluesky, Hacker News (no key), Reddit threads and Context.dev's review parsers; raw bundle, then `swarm.convert`, then the core (`docs/collect-interface.md`). Checked live with `--history 5`: a Bluesky thread (20 replies, 19 participants, 22 credits, 17 s) and a Hacker News story (15 comments, 11 commenters, 4 s) ran through all signals.
- Waiting for Makeee22's reruns of the Cresci subset and Test R on the merged core.
- For Makeee22: `swarm.collect` is on `main`; switch `jobs.py` to it instead of `bluesky.py` / `contextdev.py` / `reddit_html.py` (steps in `docs/collect-interface.md`, "Switching the site").
- For Makeee22: each cluster gains `copy_gap_seconds` (`{"median": seconds, "items": n}` or `null`) and `parameters` gains `long_words`. Each cluster, and each entry of `GET /api/swarms`, gains `declared_automation` (`{"accounts": k, "of": n}` or `null`): how many members say they are automated. Show it as a neutral note ("a feed, or a swarm posing as one: check the source"), never hide a cluster for it. With `--similar-text`, `parameters` gains `similar_model`. Additions only; `docs/api.md` describes them.
- For Makeee22: `signals.created_together` counts accounts (`items`) and links already counted under their content kind, so the site's signals table should label it as such, not add it to the others. Show `accounts[].flagged` and `flagged_members` (a member that is linked but not flagged is not accused; `docs/api.md`).
- For TheSnowman99: the parameters to tune are in the design under "Parameters". Cresci 2017 is on Arde1001's machine only; `data/README.md` should say where it comes from (http://mib.projects.iit.cnr.it) and that its licence allows research use only.

### Front end + infrastructure
- Done (branch `makeee22/frontend`): **live at https://swarm.srv2159299.hstgr.cloud** (VPS behind Hostinger's Traefik, Let's Encrypt HTTPS; `deploy/README.md`). Dashboard in `frontend/site/` on the new `docs/api.md`: upload of comments + optional profiles CSV, confidence, signals and warnings, evidence per swarm, metrics at every cut with the "cut chosen with labels visible" note, synthetic badge. `frontend/api/` = the backend's `swarm.api` unchanged + `POST /api/analyze` running `swarm.core.analyze()`.
- B4 choice: **static page**, no build step, served by nginx, which also proxies `/api/` to the API container. The table above still says OPEN: for the keeper to mark.
- Done 14.11: discussion analysis as private background jobs (`frontend/api/jobs.py`: random id, `#job=` link, 3 h in memory, 20 jobs/hour, 2 at a time, 150 participants). **Bluesky from a link** (`POST /api/jobs/url`, `frontend/api/bluesky.py`): the whole thread plus each participant's newest 30 posts, replies and reposts and profiles, through Context.dev with a direct fallback; all four signals run (text, link, repost, reply). **Reddit from a saved page** (`POST /api/jobs/reddit`). Who collects and who converts: `docs/collect-interface.md`.
- Doing: nothing running. Next candidate: a Hacker News collector (`docs/collect-interface.md`). Not deployed yet: the Bluesky link card is tested on the VPS as a separate project, the live site still has the earlier build.
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
