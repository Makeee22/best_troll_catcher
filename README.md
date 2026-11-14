# Spot the swarm

Finds **groups of accounts that act as one**: bot networks, astroturfing and brigading. It judges accounts by what they share and how (the same text, the same links, the same reposts, replies to the same posts, far more often than chance predicts), never by a single post. Every group comes with a confidence and the evidence behind it.

- **Live:** https://swarm.srv2159299.hstgr.cloud
- **Source:** https://github.com/Makeee22/best_troll_catcher (MIT licence)
- Built at Junction 2026 for Hostinger's "Decode the Noise" challenge, with Context.dev collecting comments from the live web.

It has two parts:
1. **The core** (`backend/`): an open-source program you run on your own machine. Input: a CSV of comments in one standard format for any website, plus an optional CSV of profiles. Output: the clusters of accounts that are probably coordinated, each with its evidence. It is purely algorithmic: no language model decides who is flagged, and it needs no accounts or paid services.
2. **The website**: runs the core on Hostinger, collects a discussion from a link, and can explain a cluster's evidence in plain language.

## Use the website

Open https://swarm.srv2159299.hstgr.cloud. There are three ways in.

**1. A link to a discussion.** Paste a link into "Analyse a discussion from a link" and press **Analyse the discussion**. These work:

| Site | Link | What is read |
|---|---|---|
| Bluesky | `https://bsky.app/profile/NAME/post/ID` | the whole thread, then each participant's newest posts and profile |
| Hacker News | `https://news.ycombinator.com/item?id=N` | the whole story, then each commenter's newest comments |
| Reddit | `https://www.reddit.com/r/NAME/comments/ID/…` | the comments Reddit shows before "load more" (about 25), then each commenter's newest comments |
| Review pages | Google Maps place, App Store, Google Play, Tripadvisor, Yelp, G2, TikTok video | the reviews or comments (no histories) |

A progress line shows what is being fetched. A large thread takes a few minutes, since each participant's history is one request. The result has its own private address (`#job=…`) that you can share; it is deleted after 3 hours.

**2. A saved Reddit page, for more comments.** Open the thread on reddit.com, click "View more comments" a few times, save the page (Ctrl+S, on a Mac ⌘+S), and choose the `.html` file in "Analyse a saved Reddit page".

**3. Your own CSV.** Upload a `comments.csv` (and optionally `profiles.csv`) in "Analyse your own comments (CSV)". The format is under "Expected file format" on the page and in [`docs/api.md`](docs/api.md). **Run the synthetic sample** shows a result on simulated data with known swarms. Note: an uploaded file becomes the shared demo result that every visitor sees, so upload only data you may show publicly.

**Reading the result:**
- **Summary:** what was read (for a link: comments found against the site's own count, histories fetched, seconds, credits), the warnings, and which signals ran. A "Synthetic data" badge marks simulated data.
- **Flagged accounts:** an account is flagged when it is in a group of at least 3 accounts linked by sharing content more often than chance, and enough of its own content is shared with the group. A member that is only linked to the group is listed but not flagged.
- **Swarms and their evidence:** per group, the confidence, what they share most, each member's own content shared with the group, how fast copies follow each other, creation dates close together, accounts that say they are automated, and a graph of who is linked to whom.
- **Explain this swarm with AI** writes a plain-language reading of that evidence, cites it, weighs the innocent explanations (breaking news, a real campaign, a feed), and checks the news for the most shared items. It never decides who is flagged, and usernames are replaced with "Member 1…" before anything is sent.
- **How good is the detection on this data?** appears when the data has labels: precision, recall and false-positive rate at each confidence cut.

**A flag is a lead to check, not proof.** Confidence is how much of the members' own content the group shares, not a probability. A harmless feed that posts the same wire text looks exactly like a swarm.

## Run the core on your own machine

You need Python 3.12 or newer and git. On Windows, use `.venv\Scripts\python` where it says `.venv/bin/python`.

```bash
git clone https://github.com/Makeee22/best_troll_catcher.git
cd best_troll_catcher/backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Try it on the synthetic sample** (simulated accounts with two known swarms and innocent look-alikes):

```bash
.venv/bin/python -m swarm.synthetic sample/                     # writes sample/comments.csv and sample/profiles.csv
.venv/bin/python -m swarm sample/comments.csv --profiles sample/profiles.csv
```

It prints the signals that ran, each cluster with its size and confidence, and the precision and recall on the sample's labels. One of the three clusters is a feed whose accounts say they are automated: an innocent look-alike that the core marks rather than hides, so it counts as 3 false positives. Add `--out result.json` for every cluster's evidence.

**Your own data:** write `comments.csv` with at least `username` and one of `text`, `links`, `repost_of` or `parent_id`. Add `timestamp`, `comment_id` and `thread_id` if you have them, and an optional `profiles.csv` (`username`, `created_at`, `label`, …). Every column is in [`docs/api.md`](docs/api.md), "Input files". Missing columns are fine: the core warns and skips the signals that need them.

```bash
.venv/bin/python -m swarm comments.csv --profiles profiles.csv --out result.json
.venv/bin/python -m swarm comments.csv --similar-text           # also count reworded copies (downloads a ~512 MB model once)
```

**Large files:** the core keeps its working data in a temporary database and uses at most half the machine's memory, spilling the rest to disk. Set `SWARM_MEMORY_LIMIT=2GB` (or any size) to change that, e.g. on a shared server.

**Collect a discussion from a link** (needs network; Bluesky and Hacker News need no key; Reddit and review pages need a [Context.dev](https://context.dev) key in `CONTEXT_DEV_API_KEY`):

```bash
.venv/bin/python -m swarm.collect "https://news.ycombinator.com/item?id=N" out/   # writes bundle.json, the two CSVs and result.json
```

**Convert a saved page** (a Reddit thread you saved, or a page with schema.org comment markup) into the two CSV files: `.venv/bin/python -m swarm.convert page.html out/`.

**Serve a result to the dashboard's API** on port 8000: `RESULT_FILE=result.json .venv/bin/uvicorn swarm.api:app`. **Run the whole website locally:** `docker compose up --build` from the repository root, then open http://localhost/ (details in [`frontend/README.md`](frontend/README.md)).

**Tests:** `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q`.

## How it works, in short

For each kind of content (identical text, links, reposts, replies to the same post, and optionally reworded text) the core counts what each pair of accounts shares and tests it against what chance would give, from how common each item is and how much each account posts. Pairs that pass, with the false discovery rate controlled across all pairs, become links; linked accounts form clusters. Each cluster's confidence is the share of its members' own content that the group shares. The method and its reasons are in [`docs/core-design.md`](docs/core-design.md).

## How well it works (measured; details in [`PLAN.md`](PLAN.md), Results)

| Data | Precision | Recall | False-positive rate |
|---|---|---|---|
| Cresci 2017 (Twitter, 2014; 9,076 bots, 1,083 humans) | 1.000 | 0.766 | 0.000 |
| Cresci 2017, one 7-day window, 10 comments per account (`docs/test-a-conversation.md`) | 0.997 | 0.910 | 0.006 |
| Cresci subset with 377 humans next to 4,528 bots | 0.977 | 0.982 | 0.281 |
| Community-reported Reddit bots, 2026 (`docs/test-r-reported-bots.md`) | 0.909 | 0.139 | 0.010 |

Labels are used only to measure, never to train. The one value chosen with the labels visible is the confidence cut. Simulated swarms planted into real accounts (`python -m swarm.inject`) are labelled as simulated.

**Known limits:**
- A lone bot is out of scope: it takes a group.
- Bots that reword everything are found only with `--similar-text`.
- A very large, very active botnet makes its own copies look common and partly hides itself.
- Humans closely tied to a botnet can be flagged with it (the subset row above).
- Most of 2026's reported Reddit bots shared no identical text, so recall there is low.

The full list is in `docs/core-design.md`, "Known limits"; the next tests are in [`docs/test-plan-broad-data.md`](docs/test-plan-broad-data.md).

## Repository

| Path | What |
|---|---|
| `backend/` | The core (`swarm/`), the collector (`swarm/collect/`), the converter and tests |
| `frontend/` | The website: static page (`site/`) and its API (`api/`) |
| `deploy/` | How it runs on the Hostinger VPS |
| `docs/` | Design, result format (`api.md`), collection contract, test reports |
