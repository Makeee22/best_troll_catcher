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
- **Backend (Arde):** Done, on `main` since `bac6acd`, with one change to the proposal: the member cut is **relative**. A member is flagged when its `copied_share` is at least half its cluster's `confidence` (`parameters.member_ratio` = 0.5; the value was not tuned, but the relative form replaced a fixed cut after a labelled run). A fixed 0.5 flagged no member of the synthetic swarms (6 copies among 16 posts = 0.375) and cut Test A recall from 0.94 to 0.62; the relative rule costs less (Test A 7 d at 10: 0.940 to 0.910, Cresci full 0.791 to 0.766) and removes a few humans (Test A 30 d at 20: 11 to 8). It should remove most of the 266 subset humans (their share 0.32 against the cluster's 0.79), but the subset is on your machine: **please rerun it**. Fields: `accounts[].flagged`, `flagged_members` (list and detail), metrics count flagged members only (`docs/api.md`).

**Q2. Large botnet hides itself (1a at 20 comments, 1b at 50 accounts).** Still open after `b267a68`. Ideas: cap the weight of items shared by very many accounts in the chance rate, compute the rate per signal or per item-popularity band, or treat "a group sharing many long texts" as evidence on its own. Your call; the front end can rerun Test A and the Reddit-background inject within 15 minutes of a push.
- **Backend (Arde):** Not solved tonight; it stays an open limit. One related addition: two accounts created within 30 days of each other count one more shared item on top of shared content (`created_together`), and only where that makes the test stronger. It changes nothing on Cresci or Test A (measured) and is aimed at Test R's phrase-pasting network.

**Q3. `similar_text` in the site's analyses.** It is what finds edited/reworded swarms (1b) but is off in every live job. Needs `model2vec` and the ~512 MB multilingual model in the API image, ~2 GB RAM while loading (VPS has 8 GB; two analyses may run at once), and seconds per job. Proposal: turn it on for link jobs, download the model at image build time (not at first request), keep the English model as a lighter option. Since the URL→result path is now yours: will you switch it on in the collector/analyze path, or should the front end do it in `frontend/api/jobs.py` until your path replaces it?
- **Backend (Arde):** Yes, on in the URL→result path (mine), on `main` since `bac6acd`: `model2vec` is in `backend/requirements.txt`, so your image installs it; the model is loaded once per process (not per job); `python -m swarm.similar download` fetches it, so add `RUN python -m swarm.similar download` after `COPY backend/swarm swarm` in `frontend/api/Dockerfile` (the backend's own `Dockerfile` already does). Above 50,000 distinct texts it compares by hashing, up to 1,000,000 (400,000 in about a minute). Until the collector replaces `jobs.py`, pass `similar_text=True` to `analyze()` there. Memory: about 2 GB while loading, once.

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

## 5. Backend → front end: suggestions after the switch (14.11 late evening)

From Arde1001 after reading `fd55883` against the collector's interface. The switch matches the interface; these are suggestions, in order of importance. **Answer under each** with `**Front end (Makeee22):** …`.

**S1. Links without `https://` are rejected (bug).** `POST /api/jobs/url` checks `mod.matches(url)` on the raw input, but the collector adds the scheme itself only later. Measured: `news.ycombinator.com/item?id=1` and `www.reddit.com/r/x/comments/abc/t/` match no site, so the page answers "not supported yet"; Bluesky links happen to match either way. Fix: prepend `https://` when the input has no scheme before the check (as the old Reddit branch did), or call `swarm_collect.collect()` and let its `CollectError("This site is not supported yet: …")` answer.
- **Front end (Makeee22):** Already handled in `fd55883`: `start_url_job` adds `https://` before the `matches()` check (both your examples match, checked); the measurement probably called `matches()` on the raw input. Tightened to a real scheme check (`^https?://`) in `site: weak band`.

**S2. Label the lowest confidence band.** On the backend's local runs (Cresci and Test A, development data; numbers go into `PLAN.md` Results after the refinement round), every flagged human sat in a cluster with confidence 0.2–0.4, and no cluster at 0.4 or above held a human. Proposal: show clusters at 0.2–0.4 as **"weak"**, with one line: "Groups this weak have included genuine accounts in our tests." Do not hide them, and do not raise the cut: that would be tuning on labels, and the Cresci subset shows chained humans can sit in a cluster at 0.79.
- **Front end (Makeee22):** Done: confidence under 0.4 shows a "weak" tag with that line (tooltip, and a note in the swarm's evidence). Nothing hidden, cut unchanged. Note: the synthetic demo's 8- and 5-account swarms (0.375) now show as weak.

**S3. Credits per job are approximate when two jobs run at once.** `_run_link` shares one `ContextDev` client across jobs (right: it keeps the plan's 2-request limit) and takes `credits_used` as the difference before and after, so two concurrent jobs count each other's requests. Either label it "about N credits" or keep it as is; the total is right.
- **Front end (Makeee22):** Kept as is for now.

**S4. Reddit coverage line.** A Reddit link reads what the rendered page shows before "load more" (live check: 23 of 322). The warning now says "the rest were not loaded on the page, e.g. behind Reddit's 'load more'". Proposal: next to it, point to the "Analyse a saved Reddit page" card for more comments.
- **Front end (Makeee22):** Done: the Reddit link banner names that card ("open the thread, load more, save the page and use 'Analyse a saved Reddit page'").

**S5. No change to the history length yet.** On Test A, recall jumps up and down by whole botnets as the history grows, instead of changing smoothly, because a large botnet's own copies make its items look common (open item Q2/Q3). So keep 25 (Reddit) and 30 (Bluesky) until that is fixed; 10 would save credits, but it is not better detection.

Already done on the site, for the record: member flags shown and used in the explanation, `signals.created_together` labelled as adding to other links, the similar-text model in the image.

**S6 (after Test F, 14.11 night): please soften the "weak" tag from S2.** J0l3s's Fox8-23 run (`docs/test-fox8-and-tweets.md`) found a botnet that is 100% bots at confidence 0.24–0.28: the bots' own ChatGPT text, which nobody copies, dilutes their copied share. So "groups this weak have included genuine accounts" now marks a pure botnet (and the synthetic demo's swarms) as doubtful. Until the backend's fix below is in: drop the word "weak" and say only "confidence is how much of their posts the group shares, not a probability". The backend is changing confidence to count only the kinds of content that link the cluster (Fox8: about 0.6 expected); after that, the dashboard can show the measured precision per band instead. On S1: you are right, `start_url_job` already adds the scheme; I tested `matches()` on the raw input.
- **Front end (Makeee22):** Done (14.11 ~23:00): no "weak" tag or dashed outline anywhere; the confidence tooltip, the swarm's evidence and the swarm map say only "how much of their posts the group shares, not a probability". The AI summary of a whole result (new, `POST /api/explain` and `/api/jobs/{id}/explain`) is told to judge strength from the evidence as a whole, not from the confidence number, because a real botnet with its own generated text can score low. Ready to show measured precision per band once your confidence change is in.

**S7 (14.11 night): the product is a monitoring tool; please say so on the page.** Team decision (`PLAN.md` B15): the backend now favours finding more of each botnet over never flagging a real person, so the false-positive rate will rise somewhat. The page must be honest about it, next to the flagged accounts and in the AI explanation: "Flagged accounts are worth watching, not proven bots. Some of them are real people. Use this to monitor accounts, never to ban or restrict them." Keep showing the measured false-positive rate where labels exist. The README says the same.
- **Front end (Makeee22):** Done (14.11 ~23:45): the sentence stands as a note under "Flagged accounts" and in the private-result banner; both AI explanations (one swarm, whole result) are told to say it once and never to suggest bans, suspensions or restrictions. The measured false-positive rate is still shown where labels exist.

## 6. Front end → backend: why real threads give 0 swarms (14.11 night)

From Makeee22 to Arde1001. The user keeps pointing the site at threads that *look* botted and gets 0 swarms every time. Below are four cases, run through `swarm.collect` / the core of `main` (similar-text on), with what the raw data shows. Aggregates only. **Please answer under each request (R1…R6) with `**Backend (Arde):** …`**: what the backend can do, what it cannot, and what we should say instead.

### 6a. The four cases

**Case 1. Bluesky political thread** (`bsky.app/profile/xelahart.bsky.social/post/3n2bmeer5es2t`, 14.11.2026, US politics, heated). 138 credits, 4,426 comments from 248 accounts, every signal used, **0 links in every signal, 0 clusters**.
- **Coverage:** Bluesky counts 817 replies; **289 could be read** (528 "deleted, hidden or blocked" according to the note). 254 participants; histories for the first 150 only, so **97 of the 243 repliers have no history** at all.
- **What is in it:** 0 identical reply texts between accounts; median reply 13 words. The replies that read like trolling (insults with a repeated slur-like tag) all come from **one** account (6 replies, created Nov 2024, 22 history posts in the same tone): a lone account, out of scope by design. Phrases shared by 4–6 accounts are echoes of the post itself.
- **Raw overlap the test throws away:** 369 items shared by 2+ accounts (222 replied-to posts, 147 reposts); **321 account pairs share 2+ items, 94 share 3+**, yet 0 links. These are the popular posts of one heated thread (one sub-reply has 18 repliers), so the chance test rightly calls them common. Likely the honest answer is "no coordination", but the user cannot see why.
- **Creation dates:** 131 of 243 repliers were created in Nov 2024 (Bluesky's sign-up wave after the US election), so `created_together` cannot mean much on Bluesky for that month.

**Case 2. Reddit crypto "shill" thread** (r/CryptoMoonShots, a coin launch post, 16.12.2024). 23 credits, 347 comments, 23 accounts, 0 clusters.
- 22 replies within 90 minutes of the post, all praise in the same few themes (community, dev team, still early, price target). A human reads it as a raid or paid shilling.
- **Each account wrote its own sentence:** 0 identical texts; similar-text cosine between the 18 replies: median 0.19, **max 0.60** against the cut 0.90.
- **History is the wrong time:** the thread is from Dec 2024, the 25 newest comments per account are from 2025–2026; only 3 accounts had any comment from Nov 2024–Jan 2025. Whatever else they shilled together then is out of reach.
- Reddit link: 22 of 104 comments read ("load more").

**Case 3. FiveThirtyEight IRA troll tweets, a sample** (`venalaiset_trollitwiitit_otos.csv`: 4,831 tweets, 216 IRA accounts, Jan–Sep 2017; converted to the standard format, retweets as `repost_of` rows with empty text, like the Bluesky converter). 0 clusters; text 5 links, link 4, repost 1, similar-text 3.
- **A random sample destroys the overlap:** median **6 tweets per account over 9 months**; only 55 of 5,726 items are shared by 2+ accounts, none by more than 3; 9 pairs share 2+ items.
- All accounts are trolls, so recall only (no humans for false positives). Converter: `tools/ira_to_csv.py` on Makeee22's machine (outside the repo); data in `data/raw/russian-trolls/` (ignored). Source and licence still need a line in `data/README.md` (TheSnowman99).

**Case 4. "Russian bots in a YouTube comment section".** Not a supported site. A CSV export would work, but YouTube shows no commenter history, so only in-thread signals run, and each bot posting once gives at most one shared item per pair.

### 6b. The pattern

The core finds **copy-paste and amplification swarms** (same text, link, repost or reply target, repeated). What the user brings are mostly (1) **raids in own words**, (2) **old threads** whose coordination is outside the newest-N history, (3) **lone loud accounts**, and (4) **partial threads** (Bluesky 289/817, Reddit ~25/100+, 150-history cap). The result page says "0 swarms" and nothing about which of these applied.

### 6c. Requests to the backend

**R1. Bluesky coverage: 289 of 817.** Is the gap really deleted/hidden/blocked posts, or a limit of `getPostThread` (depth, branching, replies the AppView leaves out)? If it is a limit, can the collector page through it (e.g. fetch deeper sub-threads, or `searchPosts` for replies to the root)?

- **Backend (Arde):** Measured on case 1 (15.11, counts only): every missing reply is a **direct reply to the root**: the root counts 748, `getPostThread` serves 195; every nested post is complete (sum of `replyCount` 848, 293 served, 3 posts short). `getPostThreadV2` (134 top-level + 29 hidden "other replies") returns a **subset** of those 195, so there is nothing to page through publicly. Not ours to fix: the note now says "Bluesky's public API does not return the other N (deleted, blocked, from removed accounts, or withheld)" instead of claiming why, and the result carries it as `diagnostics.reasons` `partial_thread` (on `main` from `arde/night`, `64bc287`).

**R2. History around the thread's date, not the newest N.** For an old thread the newest posts say nothing. Bluesky `getAuthorFeed` has a cursor, Hacker News Algolia has `numericFilters=created_at_i`; can the collector fetch each participant's posts from the thread's date ±N days (Reddit: whatever Context.dev's `reddit-user` parser allows)?

- **Backend (Arde):** Done (on `main` from `arde/night`, `5d7e9ec`). Hacker News: Algolia `numericFilters=created_at_i` of the story's date ±7 days, the newest comments only when none fall in it. Bluesky: `getAuthorFeed` paged back (at most 5 x 100) to the thread's date, the 25 posts nearest it kept; the newest when nothing is near. Reddit: unchanged (Context.dev's `reddit-user` parser gives the newest posts only). `diagnostics.main_thread.other_near_thread` shows how much of the history is near the thread (HN 46181371: 1.4% before, 100% now; reason `histories_far` under 20%).

**R3. Which participants get a history when there are more than 150?** Today the first 150. Proposal: the accounts with most replies in the thread, then the youngest accounts, then the rest; or raise the cap for Bluesky/HN, which cost no Context.dev credits for histories (are they fetched through Context.dev now? Case 1 used 138 credits).

- **Backend (Arde):** Done (on `main` from `arde/night`, `5d7e9ec`). Order: most posts in the thread first, ties in thread order ("youngest first" is not possible: the age is only known after the profile fetch). Bluesky histories now go to the public API directly (they went through Context.dev; that was case 1's 138 credits); the thread and the profiles still use Context.dev. Default cap **500** on Bluesky and Hacker News, 150 on Reddit (`max_participants=None` takes the site's own; **the site passes its own `MAX_PARTICIPANTS`, so raise or drop it in `jobs.py`**). Case 1 rerun: 254 of 254 histories, 168 s, 13 credits, **1 cluster of 6 flagged** (repost links only, reposts ~30 min apart, unaudited); thread-only accounts 4 of 254.

**R4. A "same-thread burst" signal for raids in own words (research question, not tonight).** Many accounts replying to one post within a short window with the same stance, and the *same set of accounts* doing it again in another thread. Only the second part is evidence of coordination; the first alone is every popular post. Is this testable on the data we have (Test R's networks, Fox8), and with what false-positive check?

- **Backend (Arde):** Prototyped 15.11 night outside the core, on Cresci (replies and times; aggregates only). Account pairs replying to the same 2+ posts at any time (what the `reply` signal already counts): bot-bot 731, human-human 561. Within 15 minutes 2+ times: bot-bot 50, human-human 247; **3+ times: bot-bot 0, human-human 142**. A same-day shuffle of which post each reply answers gives human-human 9 and 0, so the bursts are real, but in Cresci they are **people in conversation**, not bots. **Not built:** as a signal it would flag humans. Cresci's bots are spam and retweet networks, not raiders, so Fox8 or Test R may differ; the script takes any standard-format files with labels (ask Arde). What R2/R3 already change for raids: the participants' histories now come from around the thread's date, so raiders who also hit other threads that week share `reply` items there, and the existing chance test judges them.

**R5. Explain a 0-swarm result.** Can the result carry the numbers that say *why* nothing was found, so the page and the AI summary can show them: coverage (read/expected replies, participants with history), pairs that shared 2+ items but failed the chance test, the largest shared item, and the share of the history that falls in the thread's time window? Case 1 would then read: "321 pairs shared 2+ items, all of them popular posts in this thread; 97 repliers had no history".

- **Backend (Arde):** Done (on `main` from `arde/night`, `b0c4900`): `diagnostics` (every result) and `collection` (runs from a link), both in `docs/api.md` and passed by `GET /api/swarms`; **`jobs.py` builds its own listing, so pass both through there**. `diagnostics.reasons` is a list of `{code, text}` ready for the page and the AI summary: `capped_histories`, `partial_thread`, `thin_histories`, `nothing_shared_enough`, `explained_by_chance`, `no_group`, `below_cut`, `histories_far`. HN 46181371 now reads: "248 of 248 account pairs that shared 2 or more items shared no more than chance gives accounts this active. The most widely shared item: 114 accounts replied to the thread's opening post."

**R6. A converter for the IRA tweets** (`swarm/ira.py`, like `cresci.py`) and a **time-window slice** (all tweets of one week or month from the full FiveThirtyEight files, not a random sample), so we can measure recall on real troll networks. Is it worth doing before submission, or after?

- **Backend (Arde):** After submission. A random sample cannot measure recall (handoff 6a, case 3), and a time-window slice gives recall only: every account is a troll, so false positives need a human background mixed in, which we do not have tonight.

The front end will show whatever R5 returns on the page and pass it to the AI summary as evidence.

### 6d. Your branch `arde/group-test` on our local data (15.11 00:10)

Run on Makeee22's machine at `8600aa2`; rows are in `PLAN.md` Results.
- **Cresci subset:** precision 1.000, recall 0.987, **FPR 0.000** (106 humans flagged on `002022e`, now 0; 20 more bots found). All 4,859 accounts still sit in **one cluster**: the humans are chained in but no longer flagged, thanks to the copied share per linking kind. 87 s.
- **Test R:** unchanged (0.909 / 0.139 / 0.010).
- **IRA sample:** 0 clusters; the group test adds 5 links, not enough for a group (case 3 above: the sample is too thin).
- If you need the data files themselves rather than these runs, say which: the Cresci subset is research-use only and Test R holds real Reddit usernames, so neither goes through the repo.

### 6e. R7, URGENT: the 150-history cap makes false flags on the live site (15.11 ~00:30)

**R7. Accounts without a history are flagged for replying to the thread's most popular posts.** Hacker News story 46181371 ("I wasted years of my life in crypto"), `main`, similar-text on, 0 credits: 482 commenters, histories for the first 150, so **333 are judged on their posts in this thread only**. Result: 2 clusters (3 and 10 accounts, confidence 0.261 and 0.223), **7 accounts flagged**.
- Every link is `reply` (2 and 35 edges); no shared text, link or similar text. The shared items are replies to the **story itself** and to the **top comment** (10 of 10 members), plus 1–2 popular sub-comments.
- **All 7 flagged accounts have no history outside this thread** (2 of 2 and 5 of 5); members with a history sit at copied share 0.03–0.04 and are not flagged.
- Mechanism: an account with 2 comments here, both replies to the most-replied posts, has copied share 0.5 and is flagged; with its 25-post history the same two replies would be about 0.07.
- Copy gaps are hours (median 8,042 s and 17,702 s), nothing like a swarm. These are very likely ordinary readers. **The live site uses the same cap, so it makes these flags today.**

Proposals (yours to choose):
1. An account without a fetched history is never **flagged** (it may be listed as linked), or its copied share is not computed from thread-only posts.
2. A `reply` item whose parent is the thread's root, or a post with more than N repliers in the same thread, does not link accounts inside that thread (it is what being in the thread means).
3. Fetch histories for everyone who would otherwise be judged on thread posts only (HN and Bluesky histories cost no Context.dev credits), or raise the cap (R3).

- **Backend (Arde):** Fixed (on `main` from `arde/night`, `6e6b0e2`), with option 3 (R3 above) and a narrower option 1: option 1 as written would stop review pages from ever flagging copy-paste swarms (no histories there, so every reviewer is thread-only). Instead an account whose every post is in one thread **drops its `reply` items** before pairing; its copied text, links and reposts still count. Marked `accounts[].thread_only`. Second cause found on the way: the rate cap (`arde/group-test`) made it worse (8 flagged on the same data): popular reply targets counted as if 10 shared them, so every pair of commenters who answered both the story and the top comment linked. Replies are now **exempt from the cap**. HN 46181371: `main` 7 flagged, `arde/group-test` 8, `arde/night` **0** (150 histories) and **0** (all 482). Evaluation set (Cresci full/thinned/humans, Test A 7 cuts, planted swarms): identical to the branch without R7.

The front end can show "no history fetched" next to such accounts as soon as the result marks them.

### 6f. Backend → front end: what the site needs after `a50e8f4` (15.11 night)

All additive; nothing breaks until these are done, but the R7 fix and R5 only reach the page with them.
1. **`jobs.py` listing:** pass `diagnostics` and `collection` through (it builds its own listing; `swarm.api` already does). Show `diagnostics.reasons[].text` under an empty result ("Why nothing was found") and give them to the AI summary as evidence. Fields: `docs/api.md`.
2. **`MAX_PARTICIPANTS` in `jobs.py`:** still caps every site at 150. Pass `max_participants=None` (the collector then uses 500 on Bluesky and Hacker News, 150 on Reddit) or raise it. HN 46181371 with all 482 histories took 46 s, Bluesky case 1 with 254 took 168 s.
3. **Members:** show "seen in this thread only" next to `accounts[].thread_only` accounts.
4. **`signals.group_test`** is gone (the group test was removed); no label needed. `parameters` has `rate_cap`, no `group_loose`.
5. **Redeploy:** the live `/api/swarms` has no `diagnostics` yet (checked 15.11 night).

### 6g. Backend → front end: three new link types (15.11 night, `e5f510e`)

The collector now reads three more kinds of link (details: `docs/collect-interface.md`, section 1). Nothing in the result format changed; `docs/api.md` is as in 6f.

| Link | Example form | Histories | Credits | What to expect |
|---|---|---|---|---|
| **Mastodon** post, any server | `https://SERVER/@NAME/ID` (also `@NAME@OTHER`) | yes, near the thread's date | 0 | A server shows only the replies it has received from other servers: mastodon.social gave 52 of 126, reported as reason `partial_thread`. Usernames are `name@server`. |
| **Discourse** topic, any forum | `https://FORUM/t/SLUG/ID` | yes, near the topic's date | 0 | Every post (34/34 and 98/98 in tests). Usernames are the forum's own. |
| **Any other page** with standard comment markup (XenForo, Invision and Discourse forums, many news and Q&A sites) | any link no other module takes | no | **1** per link | One page only. Every account is `thread_only`, so only copy-paste and shared links can link them; reasons `capped_histories` and `thin_histories` say so. A page without markup fails with "This site is not supported yet: HOST (the page has no standard comment markup to read)…". |

What the site needs:
1. **The link check in `start_url_job` (`jobs.py`) now always passes:** the last collector (`generic`) matches every link. Either keep it so (unknown links become a job that fails with the collector's message after 5-20 s and 1 credit), or skip `generic` there (`any(mod.matches(url) for name, mod in swarm_collect.SITES if name != "generic")`) and offer the page read as a separate choice. Backend suggestion: keep it, the message is clear.
2. **Update the list of links that work** (the 400 message and the link card's help text): add "a Mastodon post (any server)", "a Discourse forum topic (any forum)", and "other forum or news pages with standard comment markup (one page, no commenter histories)".
3. **Platform label:** `bundle.thread.platform` is `Mastodon (SERVER)`, `Discourse (FORUM)`, or the host name for a generic page; `start_url_job` sets a platform only for Bluesky and Reddit, but `_run_link` merges the bundle's `thread` in afterwards, so the label is right once collection ends.
4. **Profile links**, if the page links usernames: Mastodon `https://SERVER/@NAME` (from `name@server`), Discourse `https://FORUM/u/NAME`.
5. **Progress:** a generic page reports no progress (one request); the stage text "Reading the thread" stays until analysis.
6. Demo candidates (0 flagged, clear reasons): a busy `discuss.python.org` topic (Discourse) and a `mastodon.social` post with replies.

