# Front end → backend: test results and open questions (14.11 evening)

From Makeee22 (front end + infrastructure) to Arde1001 (backend + collection) and his Claude. **Answer in this file**: under each question, add a line `**Backend (Arde):** …` with the decision, or change the proposal. The front end reads this file after every `git pull`. Everything here is aggregate numbers only; no usernames or comment texts.

## 1. Test results you may not have yet

### 1a. Test A rerun on the core after the unbiased chance rate (`b267a68` / `f14718f`)
Cresci 2017 cut to one time window from 2014-10-01, each account's first N comments in it (`docs/test-a-conversation.md` for the method). Rules only, cut 0.2.

| Comments per account | Recall before `b267a68` | **Recall after** | Precision after | FPR after |
|---|---|---|---|---|
| 3 | 0.28–0.32 | 0.28–0.32 | 1.000 | 0.000 |
| 5 | 0.65–0.73 | 0.65–0.73 | 1.000 | 0.000 |
| **10** | 0.000–0.026 | **0.848–0.940** | 0.994–1.000 | 0.000–0.011 |
| **20** | 0.000 | **0.352–0.358** (0.48 at cut 0.05) | 0.979–1.000 | 0.000–0.015 |
| all in the window | 0.28–0.42 | 0.28–0.42 | 0.976–1.000 | 0.000–0.015 |

The fix works at 10. **At 20 per account and above it still drops**, and per family social 1 falls to 12% (social 3 stays at ~92%). Same mechanism as before: a large active botnet makes its own copies look common.

### 1b. Planted swarms on a REAL Reddit background (`swarm.inject`, core `c759a49`)
Background: the 26 commenters of one r/worldnews thread (2026-11-14) with their 25 newest comments from Context.dev (411 comments in 311 threads). Planted swarms are simulated.

| Planted swarm | Rules only | `--similar-text` |
|---|---|---|
| 3, 5, 8, 20 accounts, 6 copied messages, 10 own posts | found 100% | found 100% |
| **50 accounts** | **0/50** | **0/50** |
| 8 accounts, 1 or 2 copied messages, 10 own posts | 0/8 | 0/8 |
| 8 accounts, 3 / 20 copied messages | 8/8 / 8/8 | same |
| 8 accounts, 6 copied messages, **30 / 100 / 300 own posts** | **0/8** | 0/8 |
| participation 0.5 / 0.25 | 6/8 / 3/8 | same |
| **edited** copies | 0/8 | **8/8** |
| **reworded** copies | 0/8 | **8/8** (0/8 before `c759a49`) |
| 1 message, 0 or 2 own posts | 8/8 | 8/8 |
| 1 message, 2 own posts, 7-word texts | 0/8 | 0/8 |
| **Real background accounts flagged** | **0 in all 20 scenarios** | **0 in all 20** |

`--similar-text` took ~3.5 min for the 20 scenarios on a laptop (model load included).

### 1c. Already in the repo, for completeness
- **Cresci subset false-positive trap** (`docs/findings-context-dev-and-subset.md`): FPR 0.706 on `AllComments_Combined.csv` vs 0.000 on full Cresci for the same humans. A human community (1,442 repost + 5,378 reply links among themselves) is chained into a 727-bot cluster by 52 human–bot links and inherits its confidence. Flagging by **each member's own `copied_share` ≥ 0.5** gives FPR 0.101 at recall 0.981 (cut chosen with labels visible).
- **Test R, community-reported Reddit bots 2026** (`docs/test-r-reported-bots.md`): precision 0.909, recall 0.139, FPR 0.010; `similar_text` changes nothing. 15 of 16 reported networks share no identical comment text in their 25 newest comments; 57% of reported accounts were already removed or suspended.
- **Full Cresci on `73def06`**: precision 1.000, recall 0.790, FPR 0.000.

## 2. What collection can get (measured through Context.dev, logged out)

| Source | Thread | Each commenter's history |
|---|---|---|
| Reddit link | Rendered HTML (`formats.html`, `waitFor` 6 s, **one retry with a longer wait** because Reddit sometimes answers with a bot check first): what a browser shows before "load more", 25 comments in every test (of 31, 196, 475, 480) | `reddit-user` parser: works, ~1 credit, 0.5–5 s each |
| Reddit saved page | Whatever was loaded (188 on your test page) | same |
| Bluesky link | **Complete** (public AppView API) | `getAuthorFeed`, complete |
| Hacker News | **Complete** (Algolia API: 1,124 comments, 717 commenters in one story) | Algolia search by author |
| X | 3 replies, then a login wall | 5–6 posts, then a login wall |

Practical limits: our plan allows **2 concurrent Context.dev requests**; latency went from 0.5 s in the morning to 5 s per request in the afternoon (a 143-participant Bluesky thread took 5.5 min). Context.dev's model-based `formats.json` **miscounted** a Bluesky thread (45 vs 157 replies): parse raw content yourself. Reddit thread `reddit-post` parser returns no comments (reported to Context.dev as feedback). Balance ~49,500 credits.

## 3. Questions and proposals for the backend

Each has the front end's proposal. **Please answer under each one.**

**Q1. Member-level flagging (the false-positive trap, 1c).** A cluster's confidence is passed to every member, so a human community bridged into a botnet is flagged wholesale. Proposal: in the result, mark each member `flagged: true` only when its own `copied_share` ≥ a member cut (0.5 measured best on the subset), keep low-share members listed as "linked, not flagged", and count metrics on flagged members. The front end will show the two groups separately as soon as the field exists.
- **Backend (Arde):** Done on branch `arde/detect-fixes` (pushed when Arde says so), with one change to the proposal: the member cut is **relative**. A member is flagged when its `copied_share` is at least half its cluster's `confidence` (`parameters.member_ratio` = 0.5, fixed before measuring). A fixed 0.5 flagged no member of the synthetic swarms (6 copies among 16 posts = 0.375) and cut Test A recall from 0.94 to 0.62; the relative rule costs less (Test A 7 d at 10: 0.940 to 0.910, Cresci full 0.791 to 0.766) and removes a few humans (Test A 30 d at 20: 11 to 8). It should remove most of the 266 subset humans (their share 0.32 against the cluster's 0.79), but the subset is on your machine: **please rerun it**. Fields: `accounts[].flagged`, `flagged_members` (list and detail), metrics count flagged members only (`docs/api.md`).

**Q2. Large botnet hides itself (1a at 20 comments, 1b at 50 accounts).** Still open after `b267a68`. Ideas: cap the weight of items shared by very many accounts in the chance rate, compute the rate per signal or per item-popularity band, or treat "a group sharing many long texts" as evidence on its own. Your call; the front end can rerun Test A and the Reddit-background inject within 15 minutes of a push.
- **Backend (Arde):** Not solved tonight; it stays an open limit. One related addition: two accounts created within 30 days of each other count one more shared item on top of shared content (`created_together`), and only where that makes the test stronger. It changes nothing on Cresci or Test A (measured) and is aimed at Test R's phrase-pasting network.

**Q3. `similar_text` in the site's analyses.** It is what finds edited/reworded swarms (1b) but is off in every live job. Needs `model2vec` and the ~512 MB multilingual model in the API image, ~2 GB RAM while loading (VPS has 8 GB; two analyses may run at once), and seconds per job. Proposal: turn it on for link jobs, download the model at image build time (not at first request), keep the English model as a lighter option. Since the URL→result path is now yours: will you switch it on in the collector/analyze path, or should the front end do it in `frontend/api/jobs.py` until your path replaces it?
- **Backend (Arde):** Yes, on in the URL→result path (mine). On the branch: `model2vec` is in `backend/requirements.txt`, so your image installs it; the model is loaded once per process (not per job); `python -m swarm.similar download` fetches it, so add `RUN python -m swarm.similar download` after `COPY backend/swarm swarm` in `frontend/api/Dockerfile` (the backend's own `Dockerfile` already does). Above 50,000 distinct texts it compares by hashing, up to 1,000,000 (400,000 in about a minute). Until the collector replaces `jobs.py`, pass `similar_text=True` to `analyze()` there after the push. Memory: about 2 GB while loading, once.

**Q4. Handover of the live job path.** `frontend/api/jobs.py` today: `POST /api/jobs/url` (Bluesky and Reddit links), `POST /api/jobs/reddit` (saved page), `GET /api/jobs/{id}`, `GET /api/jobs/{id}/swarms/{sid}`, `POST /api/jobs/{id}/swarms/{sid}/explain`; private random id, 3 h TTL, 20 jobs/hour, 2 running. The page depends on the public job shape (`status`, `stage`, `progress`, `thread`, `histories_ok/failed`, `credits_used`, `seconds`, `listing`, `metrics`). Proposal: you keep that shape (or tell us the new one in `docs/api.md`), and the front end switches `jobs.py` to call `backend/swarm/collect` the moment it is on `main`. Which function should we call, and what does it return?
- **Backend (Arde):** Keep the job shape and the endpoints in `jobs.py`; I will not change them. The collector will be `swarm.collect.collect(url, *, history=25, max_participants=150, on_progress=None) -> bundle` (the raw bundle of `docs/collect-interface.md`, with `coverage`, `credits_used` and a `thread` summary like yours), then `swarm.convert.convert(bundle)` and `swarm.core.analyze(...)`. I will announce it in `docs/collect-interface.md` when it is on `main`.

**Q5. Fields the explanation depends on.** `frontend/api/explain.py` reads from each cluster: `size`, `confidence`, `first_seen`, `last_seen`, `accounts[].username/copied_share`, `edges[].kind`, `edge_count`, `top_items[].kind/value/accounts/first_seen/last_seen`, `copy_gap_seconds`, `created_within_30_days`, `declared_automation`, and `source.comments_file/synthetic`. Please keep them (or announce a change in `docs/api.md`).
- **Backend (Arde):** Kept, all of them. Additions only: `accounts[].flagged`, `flagged_members`, `edges[].created_together`, `signals.created_together`, `parameters.member_ratio` and `parameters.created_days` (`docs/api.md`). The explanation could say how many members are flagged and that unflagged ones are only linked.

**Q6. Bluesky rows.** Your converter now reads Bluesky (`a260375`). The site still converts Bluesky in `frontend/api/bluesky.py`. Proposal: the front end switches to `swarm.convert` for Bluesky as it did for Reddit, using `pages[].json` (raw API responses: `getPostThread`, `getAuthorFeed`, `getProfiles`). Is the expected page shape the one in `docs/collect-interface.md`, and does `convert()` emit reposts as `repost_of` rows?
- **Backend (Arde):** Yes: `pages[].json` with the raw `getPostThread`, `getAuthorFeed` and `getProfiles` responses, as in `docs/collect-interface.md`. `convert()` emits reposts as rows with empty text and `repost_of` (id `repost:HANDLE:URI`), skips self-reposts, and uses the DID for `handle.invalid`, as your `bluesky.py` does. Bluesky collection moves into `swarm.collect` anyway, so you can wait for it.

## 4. What the front end shipped this evening (live at https://swarm.srv2159299.hstgr.cloud)
- Link card: Bluesky post links (whole thread + participants' 30 newest posts, replies and reposts) and Reddit thread links (rendered page through `swarm.convert`); saved Reddit page card; CSV upload; synthetic demo.
- Reddit jobs use `swarm.convert` (the `<br>` bug is gone).
- **"Explain this swarm with AI"**: Hostinger AI Router (`gemini-3.5-flash-eu`, run in the EU), Google Gemini API as fallback. The model only reads the core's evidence, cites it (E…, F…, N…), weighs innocent explanations, gives no verdict; usernames become "Member 1…" before sending; cached; 60/hour.
- **News check** inside the explanation: Context.dev news search for the 3 most shared items in the group's active window ±2 days; the model judges the breaking-news look-alike from it. Tested on a real headline: the model rated "real users sharing breaking news" as high, citing three same-day articles.
