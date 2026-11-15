# Spot the swarm

Finds **groups of accounts that act as one**: bot networks, astroturfing and brigading. It judges accounts by what they share and how (the same text, the same links, the same reposts, replies to the same posts, far more often than chance predicts), never by a single post. Every group comes with a confidence, the evidence behind it, and, when nothing is found, the reasons why.

- **Live:** [https://swarm.srv2159299.hstgr.cloud](https://swarm.srv2159299.hstgr.cloud/)

- **Source:** [https://github.com/Makeee22/best\_troll\_catcher](https://github.com/Makeee22/best_troll_catcher) (MIT licence)

- Built at Junction 2026 (13–15.11.2026) for Hostinger's **"Decode the Noise"** challenge and the **Context.dev** challenge ("a product that reacts to the live web").

## Goal and vision

Coordinated accounts make a few voices look like many: a botnet pushing a link, a paid campaign praising a product, a raid on a thread. One post at a time, each account looks ordinary. Together they are not: they copy each other, share the same links and answer the same posts, far more often than real people do by chance.

**Spot the swarm makes that visible to anyone who runs a comment section or studies one,** from an ordinary user to a site owner / developer, without needing a data-science team, a paid service or trust in a black box.

What is our vision for Spot The Swarm:

- **Open and free at its core.** The detection algorithm is an open-source program anyone can download and run on their own machine, on their own data, with no accounts, keys or language model. Partner technology adds convenience on top (collecting comments from a link, explaining a result in plain language) but is not required for developer work.

- **Groups, not individuals.** A cluster is at least three accounts. Lone bots are out of scope by design.

- **Honest detection.** A language model does not decide who is flagged; the rules are deterministic statistics. Labelled data measured the detection and never trained it. Every number the tool shows identifies what it was measured on. The tool can and does get false positives and should not be used as the sole basis for decisions on e.g. banning accounts, but to identify suspicious traffic.

## The two parts

1. **The core** (`backend/`): CSV of comments (and optionally profiles) in one standard format for any website → clusters of accounts that are probably coordinated, each with a confidence and its evidence, plus diagnostics that explain the result. Purely algorithmic, deterministic, and fast enough for millions of comments even on a laptop.

2. **The website**: runs the core on Hostinger, collects a discussion from a link, and can explain a result in plain language with a language model through Gemini API.

## Use the website

Open [https://swarm.srv2159299.hstgr.cloud](https://swarm.srv2159299.hstgr.cloud/). There are three ways in.

**1. A link to a discussion.** Choose **Link** in the input menu, paste a link and press **Analyse**:

| Site | Link | What is read |
| - | - | - |
| Bluesky | `bsky.app/profile/NAME/post/ID` | the whole thread, then each participant's posts from around the thread's date, and their profiles |
| Hacker News | `news.ycombinator.com/item?id=N` | the whole story, then each commenter's comments from around its date |
| Reddit | `reddit.com/r/NAME/comments/ID/…` | the comments Reddit shows before "load more" (about 25), then each commenter's recent comments -\> See a saved reddit page below |
| YouTube | `youtube.com/watch?v=ID`, `youtu.be/ID`, Shorts, live | the newest 2,000 comment threads with replies; the channel's comments on its other videos stand in for histories (YouTube cannot list one account's comments); channel creation dates |
| Mastodon (any server) | `SERVER/@NAME/ID` | the thread as that server knows it, then each participant's posts from around its date |
| Discourse (any forum) | `FORUM/t/SLUG/ID` | every post of the topic, then each poster's activity from around its date |
| Review and comment pages | Google Maps place, App Store, Google Play, Tripadvisor, Yelp, G2, TikTok video | the reviews or comments (no histories), through Context.dev's parsers |
| **Any other page** with standard comment markup | forums on XenForo, Invision or Discourse, many news and Q&A sites | one page of comments read from its schema.org markup, through Context.dev (no histories) |


Histories are taken from the thread's date ±7 days, the most active participants first (up to 500 on the free public APIs, 150 on Reddit), so an old thread is judged on what its participants did then, not today. A progress line shows what is being fetched; a large thread takes a few minutes. The result has its own private address (`\\\#job=…`) that you can share; it is deleted after 3 hours.

**2. A saved Reddit page, for more comments** (**Saved Reddit page** in the menu). Open the thread on reddit.com, click "View more comments" a few times, save the page (Ctrl+S, on a Mac ⌘+S), and upload the `.html` file.

**3. Your own CSV** (**Your own CSV** in the menu). Upload a `comments.csv` (and optionally `profiles.csv`); the format is on the page and in [`docs/api.md`](file:///home/arde1001/Projects/hostingerChallenge/docs/api.md). The page also offers sample files with simulated swarms. An uploaded file becomes the shared demo result that every visitor sees, so upload only data you may show publicly.

**Reading the result:**

- **Summary:** what was read (comments found against the site's own count, whose history was fetched, time, credits), warnings, and which signals ran. A "Synthetic data" badge marks simulated data.

- **Why nothing was found:** when no swarm is listed, the page shows the core's reasons in plain sentences, for example "248 of 248 account pairs that shared 2 or more items shared no more than chance gives accounts this active; the most widely shared item: 114 accounts replied to the thread's opening post", or "Only 293 of the 850 comments the site counts could be read".

- **Flagged accounts:** an account is flagged when it is in a group of at least 3 accounts linked by sharing content more often than chance, and enough of its own content is shared with the group. A member that is only linked is listed but not flagged. "(this thread only)" marks accounts with no other posts, whose replies are not counted as evidence.

- **Swarms and their evidence:** per group, the confidence, the most shared items, each member's copied share, how fast copies follow each other, creation dates close together, accounts that say they are automated, and a map of who is linked to whom.

- **AI explanation** (Gemini through Hostinger's AI Router): a plain-language reading of the evidence that weighs the innocent explanations (breaking news, a real campaign, a feed) and checks the news for the most shared items. It never decides who is flagged, never suggests bans, and usernames are replaced with "Member 1…" before anything is sent.

- **How good is the detection here?** appears when the data has labels: precision, recall and false-positive rate at each confidence cut.

**A flag is a reason to watch an account, not a verdict.** Some flagged accounts are real people. Confidence is how much of the members' own content the group shares, not a probability. A harmless feed that posts the same wire text looks exactly like a swarm; the result marks accounts that say they are automated, but never hides them.

## Run the core on your own machine

You need Python 3.12 or newer and git. On Windows, use `.venv\\\\Scripts\\\\python` where it says `.venv/bin/python`.

```
git clone https://github.com/Makeee22/best\\\_troll\\\_catcher.git    
cd best\\\_troll\\\_catcher/backend    
python -m venv .venv    
.venv/bin/pip install -r requirements.txt
```

**Try it on the synthetic sample** (simulated accounts with known swarms and innocent look-alikes):

```
.venv/bin/python -m swarm.synthetic sample/                     \\\# writes sample/comments.csv and sample/profiles.csv    
.venv/bin/python -m swarm sample/comments.csv --profiles sample/profiles.csv
```

It prints the signals that ran, each cluster with its size and confidence, and precision and recall on the sample's labels. One cluster is a feed whose accounts say they are automated: an innocent look-alike that the core marks rather than hides, so it counts as 3 false positives. Add `--out result.json` for the full result with every cluster's evidence and the diagnostics.

**Your own data:** `comments.csv` needs `username` and one of `text`, `links`, `repost\\\_of` or `parent\\\_id`. Add `timestamp`, `comment\\\_id` and `thread\\\_id` if you have them, and an optional `profiles.csv` (`username`, `created\\\_at`, `label`, …). Every column is in [`docs/api.md`](file:///home/arde1001/Projects/hostingerChallenge/docs/api.md), "Input files". Missing columns are fine: the core warns and skips the signals that need them.

```
.venv/bin/python -m swarm comments.csv --profiles profiles.csv --out result.json    
.venv/bin/python -m swarm comments.csv --similar-text           \\\# also count reworded copies (downloads a ~512 MB model once)
```

**Large files:** the core keeps its working data in a temporary database, uses at most half the machine's memory and spills the rest to disk. `SWARM\\\_MEMORY\\\_LIMIT=2GB` (or any size) changes that.

**Collect a discussion from a link** (needs network). Bluesky, Hacker News, Mastodon and Discourse need no key; Reddit, the review pages and other pages need a [Context.dev](https://context.dev/) key in `CONTEXT\\\_DEV\\\_API\\\_KEY`; YouTube needs a free YouTube Data API key in `YOUTUBE\\\_API\\\_KEY`:

```
.venv/bin/python -m swarm.collect "https://news.ycombinator.com/item?id=N" out/   \\\# writes bundle.json, the two CSVs and result.json
```

**Convert a saved page** (a Reddit thread you saved, or any page with schema.org comment markup) into the two CSV files: `.venv/bin/python -m swarm.convert page.html out/`.

**Benchmark with planted swarms:** `.venv/bin/python -m swarm.inject comments.csv` plants simulated swarms of different sizes and styles into a background file and tabulates what is found (the planted accounts are labelled as simulated).

**Serve a result to the dashboard's API** on port 8000: `RESULT\\\_FILE=result.json .venv/bin/uvicorn swarm.api:app`. **Run the whole website locally:** `docker compose up --build` from the repository root, then open http://localhost/ (details in [`frontend/README.md`](file:///home/arde1001/Projects/hostingerChallenge/frontend/README.md)).

**Tests:** `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q` (236 tests, offline).

## How it works

The full method and the measurements behind each choice are in [`docs/core-design.md`](file:///home/arde1001/Projects/hostingerChallenge/docs/core-design.md).

1. **Reduce** each comment to what it can share with a copy: its normalised text, its links (without tracking parameters), the post it reposts, the post it answers, and optionally a group of reworded copies (a small multilingual embedding model, the core's only model).

2. **Test every pair of accounts against chance.** If accounts picked items at random, popular ones more often, two accounts with `n1` and `n2` items would share about `n1 × n2 × S` of them. A pair links only when it shares clearly more (Poisson test, with the false discovery rate held at 1% across all pairs), and only on two or more items, or one long text. Sharing a viral post proves little; sharing many rare ones does.

   - For copied text, an item counts toward `S` as if at most 10 accounts shared it, so a large botnet's own copies cannot make copying look normal. Links, reposts and replies keep the true rate: many people sharing one breaking-news link, reposting one viral post or answering one popular post is normal.

   - An account seen in one thread only drops its replies before pairing: replying to the thread's posts is what being in the thread means. Its copied text, links and reposts still count.

3. **Group** linked accounts; three or more make a cluster.

4. **Confidence** is how much of the members' own content the group shares, computed per kind of content and weighted by the kinds that actually link the cluster (a repost ring is not diluted by its own uncopied text). A member is flagged only when its own copied share is at least half the cluster's, so real people bridged into a botnet by a few shared posts are listed but not flagged.

5. **Diagnostics** say why the result looks as it does: what was read, how many pairs shared items and how many passed, the most widely shared items, how much of the history lies near the thread, and plain-language reasons.

**Tried and dropped** (numbers in [`PLAN.md`](file:///home/arde1001/Projects/hostingerChallenge/PLAN.md), Results): a group-level test (no measurable gain), a fixed floor for members, splitting clusters by label propagation, a second reporting route, a model-free near-duplicate signal, and a "same-thread burst" signal for raids (on real data the bursts were people in conversation, not bots).

## How well it works

Measured on the final core unless marked; per account; cut 0.2, the one value chosen with the labels visible. Details and every run: [`PLAN.md`](file:///home/arde1001/Projects/hostingerChallenge/PLAN.md), Results.

| Data | Precision | Recall | False-positive rate |
| - | - | - | - |
| Cresci 2017 (Twitter, 2014; 9,076 bots, 1,083 humans) | 1.000 | 0.833 | 0.001 (1 human) |
| Cresci 2017 humans alone (1,083) | n/a | n/a | 0 flagged |
| Cresci 2017, one 7-day window, 10 comments per account ([Test A](file:///home/arde1001/Projects/hostingerChallenge/docs/test-a-conversation.md)) | 0.996 | 0.911 | 0.008 |
| The same window, 25 comments per account (was 0.08 recall before 15.11) | 0.997 | 0.660 | 0.005 |
| Cresci subset, 377 humans next to 4,528 bots (the false-positive trap)\* | 1.000 | 0.987 | 0.000 (was 0.281) |
| Fox8-23 (Twitter botnet, 2023), held-out half, run once\* ([Test F](file:///home/arde1001/Projects/hostingerChallenge/docs/test-fox8-and-tweets.md)) | 1.000 | 0.997 | 0.000 |
| Community-reported Reddit bots, 2026\* ([Test R](file:///home/arde1001/Projects/hostingerChallenge/docs/test-r-reported-bots.md)) | 0.909 | 0.139 | 0.010 |


\* Measured by teammates on the pre-final branch (`8600aa2`, which had a group test that changed nothing measurable there); a re-run on the final core is pending for Fox8.

**Planted swarms** (`swarm.inject`, simulated, labelled so) into real backgrounds (Cresci humans, a Mastodon thread, a Discourse topic, a YouTube video's comments): swarms of 3 to 50 accounts copying 6 messages among 10 of their own are found in full; at most 2 real accounts were flagged alongside.

**Live threads (unlabelled):** a Hacker News thread where the earlier version flagged 7 ordinary readers now flags none, and says why. On YouTube, clusters of single-comment accounts posting the same 10–20-word text are found; they match known comment-copying bots but are unaudited.

**Known limits:**

- A lone bot is out of scope: it takes a group.

- Bots that reword everything are found only with `--similar-text`, and only for close rewordings; raids written in each account's own words are not found.

- A swarm that hides a few copies among 30 or more posts of its own is missed at the default cut.

- Humans closely tied to a botnet can end up in its cluster; member flags keep most of them from being flagged, not all.

- A feed that posts the same wire text is coordinated by our definition and is flagged (marked when it says it is automated).

- Accounts seen in one thread only are judged on very little; on YouTube one shared long comment gives a confidence of 1.0.

- Chinese and Japanese text (no spaces between words) gives no text item.

- Collection depends on what each site shows: Bluesky's API returns only part of a heated thread, a Mastodon server shows only the replies it has received, Reddit shows about 25 comments before "load more".

## Data and honesty rules

- Labels measure; they never train. The confidence cut is the one value chosen with labels visible, and we say so wherever results are shown.

- Synthetic and planted data is always labelled as simulated.

- Cresci 2017 is for research use only and holds real people's tweets: it is never committed, quoted or served; only aggregate numbers leave the machine. The same holds for every real dataset we tested on.

- API keys live only in `.env` and the server's environment, never in the repository, a result or a bundle.

## Built with

- **Hostinger:** the VPS the site and the core run on (Docker behind Traefik with HTTPS), and the AI Router (Gemini) for the plain-language explanations.

- **Context.dev:** collecting comments from the live web where a site needs it: Reddit threads and histories, the review and comment parsers, other pages' markup, Bluesky threads and profiles.

- **Public APIs:** Bluesky, Hacker News (Algolia), Mastodon, Discourse, YouTube Data API.

- **Python 3.12, DuckDB, FastAPI, model2vec**; a static front end served by nginx.

## Team

| Role | Who | Owns |
| - | - | - |
| Backend and collection | Arde1001 | the core, the collector and converter, `docs/api.md`, `docs/collect-interface.md` |
| Front end and infrastructure | Makeee22 | the website, the deploy, the live URL |
| Presentation and documentation | J0l3s | the submission, deck, video, demo script, this README, `PLAN.md` |
| Data and detection criteria | TheSnowman99 | datasets, labelled test sets, criteria |


## Repository

| Path | What |
| - | - |
| `backend/swarm/` | The core: `load.py`, `detect.py`, `diagnose.py`, `evaluate.py`, `core.py`, the command line, the API, `synthetic.py`, `inject.py`, `cresci.py`, `similar.py` |
| `backend/swarm/collect/` | Link → raw bundle: one module per site, `generic.py` for any page with schema.org markup |
| `backend/swarm/convert.py`, `sites.py`, `schemaorg.py` | Raw bundle or saved page → the two CSV files |
| `frontend/` | The website: static page (`site/`) and its API (`api/`) |
| `deploy/` | How it runs on the Hostinger VPS |
| `docs/` | Design (`core-design.md`), result format (`api.md`), collection contract (`collect-interface.md`), test reports, the front end ↔ backend handoff |
| `PLAN.md` | Timeline, decisions (B1–B15), every evaluation run, status per role |


Licence: MIT.

