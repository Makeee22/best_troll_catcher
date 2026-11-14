# Test plan: what a broader dataset must tell us, and how it changes the core

Written 14.11.2026 late evening by the backend owner, for whoever runs the tests (J0l3s now) and for the backend refinements that follow. It lists the questions still open after Tests A and R, the data that can answer each, how to run and report it, and which change to the core each answer would lead to. Results go into `PLAN.md` Results (one row per run) and, for a larger test, a `docs/test-<name>.md` like `docs/test-r-reported-bots.md`.

## Rules for every run (from `CLAUDE.md`)

- **Labels measure, they never train.** The one value chosen with labels visible is the confidence cut; say so wherever results are shown. Any other value changed after a labelled run (as `member_ratio`'s form was) is written down as such, and checked on data it was not chosen on (see "Development and held-out data").
- **Aggregate numbers only** leave the machine: no usernames, no comment texts, no account ids, not even in the scratch notes pasted into chat. Raw data goes in `data/raw/` or `backend/data/` (ignored). Research-only datasets follow the Cresci rule: never committed, quoted or served.
- **Synthetic or planted data is labelled synthetic**, in the data and in every table.
- Note the core's commit (`git rev-parse --short HEAD`) and the flags in each row, so a number can be traced to the code that made it.

## What we know now (details in the linked files)

| Test | Data | Result on `main` | What it says |
|---|---|---|---|
| Cresci 2017 full | Twitter 2014, 10,159 labelled accounts | precision 1.000, recall 0.766, FPR 0.000 | Strong on a dataset of large old botnets |
| Cresci thinned to 10 per account | same, 10 comments each | recall 0.714 | Works on short histories |
| Test A (`docs/test-a-conversation.md`) | Cresci cut to one time window | recall 0.758–0.910 at 10 per account, about 0.36 at 20 | **A large active botnet hides itself** at longer histories |
| Cresci subset (PLAN Results 21:20) | 4,528 social bots, 377 humans | precision 0.977, recall 0.982, **FPR 0.281** (0.706 before member flags; a fixed own-share cut 0.5 gave 0.101) | Humans bridged into a botnet's cluster are still flagged |
| Test R (`docs/test-r-reported-bots.md`) | 72 community-reported Reddit bots, 2026 | precision 0.909, recall 0.139, FPR 0.010 | Today's bots mostly do not copy each other word for word, or work alone; 57% of reported accounts were already gone |
| Planted swarms, `swarm.inject` | simulated swarms in real backgrounds | found down to 3 copied messages; missed at 50 accounts and at 30+ own posts | Limits of the chance test, measured |
| Live threads (14.11) | 1 Reddit, 1 Bluesky, 1 Hacker News thread via `swarm.collect` | all ran end to end; the Reddit thread (22 commenters, 347 comments) gave 0 clusters | The path works live; three threads are not a false-positive rate |

## The questions, in priority order

Each has: why it matters, the data that answers it, what to measure, and the decision it drives.

**Q1. Which member rule: relative (now) or a fixed own-share cut?**
- Why: the subset shows the relative rule (`copied_share` ≥ 0.5 × the cluster's confidence) still flags 106 of 377 bridged humans; a fixed cut 0.5 flags 38 but flagged no member of the synthetic swarms (share 0.375) and cut Test A recall from 0.94 to 0.62.
- Data: any labelled set with humans next to bots in one community (the subset; TwiBot-22 if available); Test A; the planted swarms.
- Measure: for each rule, FPR and recall on each set; and the distribution of `copied_share` for flagged humans vs bots (deciles only).
- Decision: keep the relative rule, switch to fixed, or combine them (flag when the share passes either the relative cut or a fixed floor, or require both). Whichever is chosen was picked with labels visible: say so, and confirm on held-out data.

**Q2. How many comments per account should the site fetch (B11)?**
- Why: Test A favours 10 (recall 0.85–0.94) over 20 (0.36); the site fetches 25 (Reddit) and 30 (Bluesky). Fewer also costs fewer credits.
- Data: Test A cuts at 5, 10, 15, 20, 25, 30 per account; Test R's histories truncated to the same lengths; planted swarms on a real background at each length.
- Measure: recall and FPR per length, per dataset.
- Decision: the collector's default `history`. If the best length differs by dataset, the large-botnet effect (Q3) is the cause and is fixed there, not by the default.

**Q3. Does a large active botnet hide itself? (handoff Q2, still open)**
- Why: when one botnet produces most copies of an item, its copies look common and the chance test forgives them (Test A at 20, the 50-account planted swarm).
- Data: Test A at 20 and 50 per account; `swarm.inject` with swarm sizes 20, 50, 100, 200 on a real background.
- Measure: recall by swarm size and by family (social 1 vs social 3 in Cresci).
- Decision: one of the ideas in `docs/handoff-frontend-to-backend.md` Q2 (cap the weight of items shared by very many accounts in the chance rate; estimate the rate per popularity band; long texts shared by a group as evidence on their own), chosen on development data, measured on held-out data.

**Q4. What do genuine communities look like to the core? (false positives on unlabelled data)**
- Why: judges weigh false positives most, and labelled human data is small and old (1,083 Cresci humans, 96 Test R background accounts). The innocent look-alikes (breaking news, a real campaign, a fan community, benign feeds, one viral post) each have a test, but only on synthetic data.
- Data: unlabelled live threads through `swarm.collect` (`python -m swarm.collect URL OUT_DIR`), chosen to stress the look-alikes: a breaking-news thread, a petition or campaign thread, a fandom or sports match thread, a giveaway, a local-news thread; on Reddit, Bluesky and Hacker News; and the review sites.
- Measure: flagged accounts per 1,000 accounts read, per platform and per thread type; for each flagged cluster, an **audit** (below).
- Decision: which signal or rule causes the false alarms (from `edges[].kind` and `top_items[].kind` of the audited clusters), and a targeted fix for that one.

**Q5. What does each signal contribute on its own?**
- Why: all signals share one chance test, so a noisy signal can hide the others (`PLAN.md`, Backend, open items).
- Data: Cresci full and thinned, Test A, Test R.
- Measure: recall and FPR with only `text`, only `link`, only `repost`, only `reply`, only `similar_text`, and all together. The simplest way is one run per signal with the other columns removed from the CSV (the core warns and skips signals whose columns are missing).
- Decision: whether to test each signal on its own and combine the p-values, instead of one shared test.

**Q6. What do today's bots share, if not identical text? (Test R's low recall)**
- Why: 15 of 16 reported networks shared no identical text; the adult network pasted 4–7-word phrases, and its members were created within 30 days of each other.
- Data: Test R, more report posts (Reddit), Bluesky moderation lists of spam accounts if public, fake-review rings on the review sites.
- Measure: for the reported networks, aggregate counts per kind of overlap: identical text, shared 4–7-word phrases, shared links or domains, same threads within minutes, creation dates close together, similar-text pairs at cosine 0.8 and 0.9.
- Decision: which new item kind is worth adding (a phrase item, a thread co-activity signal, a domain item) and whether `created_together` earns its place (it changed nothing on Cresci and Test A).

**Q7. Is the confidence honest?**
- Why: the result shows a confidence per cluster; judges will read 0.8 as "80% sure".
- Data: every labelled set.
- Measure: precision of flagged members by confidence band (0.2–0.4, 0.4–0.6, 0.6–0.8, 0.8–1.0).
- Decision: whether the dashboard shows the number, a band name, or the measured precision of the band.

**Q8. Languages and scale.**
- Why: Finnish synonym rewordings score under the similar-text cut, Chinese and Japanese give no text item (no spaces), and the site runs on 2 vCPU and 8 GB.
- Data: threads in Finnish, Spanish, Japanese; one large dataset (a million comments or more).
- Measure: similar-text items found per language on planted reworded swarms; seconds and peak memory per 100,000 comments, with and without `--similar-text`.
- Decision: a character n-gram text key for languages without spaces; the server's job limits.

## Data to look for

Check each one's licence and access terms before downloading; record source and licence in `data/README.md`. Research-only data follows the Cresci rules.

| Kind | Candidates | Answers |
|---|---|---|
| Labelled bots and humans | Cresci 2017 (have); TwiBot-22 (Twitter, about a million users, labels by annotation, access on request); other bot-repository sets (Botometer's collection) | Q1, Q2, Q5, Q7 |
| Labelled coordinated networks | Platforms' published state-backed operation archives (Twitter/X's Information Operations releases, Reddit's 2018 list of suspicious accounts; availability changed since, check); community-reported networks as in Test R | Q3, Q6 |
| Labelled fake reviews | YelpChi and YelpNYC (labels from Yelp's own filter, research use) | Q4, Q6 on review sites |
| Unlabelled backgrounds | Live threads through `swarm.collect` (Reddit, Bluesky, Hacker News, review sites); Bluesky's public Jetstream feed for a large background; Hacker News in BigQuery's public dataset | Q2, Q4, Q8, and planted swarms on real backgrounds |
| Planted (synthetic) | `python -m swarm.inject BACKGROUND.csv` on any real background above | Recall on data with no labels: Q2, Q3 |

Unlabelled data cannot give a recall, but planting simulated swarms into it can (label them synthetic), and auditing what is flagged gives a false-positive estimate.

## How to run

1. **Labelled data:** convert to the standard format (`docs/api.md`, "Input files"), with `label` set to `bot`/`bot:<network>` and `human`. Run `python -m swarm COMMENTS.csv --profiles PROFILES.csv --out result.json`, and once more with `--similar-text`. `result.json` holds `metrics` at every cut.
2. **Unlabelled links:** `python -m swarm.collect URL OUT_DIR --history 25`, which writes `bundle.json`, the CSVs and `result.json`, and prints a summary. Note the credits used (Context.dev, in the bundle) and the seconds.
3. **Planted swarms:** `python -m swarm.inject COMMENTS.csv --out inject.json [--similar-text]`; the table it prints goes into Results as is.
4. **History length (Q2):** cut each account to its first N comments by time, as in Test A, then step 1.
5. Never change a core parameter between the runs of one comparison except the one being compared.

### Development and held-out data

The refinements after these runs will be chosen by looking at results, which is a form of tuning. To keep the numbers honest:
- Split each new dataset before looking: by account (hash of the username, 50/50) or, better, by network or by thread, so a botnet is never on both sides.
- Look at and refine on the development half only. Run the held-out half **once**, after the change is final, and report both halves.
- Cresci full is already well known to the core; treat it as development data from now on. Test R and every dataset new from tonight on are split.

### Auditing a flagged cluster on unlabelled data

Two people, each on their own, read the cluster's evidence as the result shows it (`edges`, `top_items`, `copy_gap_seconds`, `created_within_30_days`, `declared_automation`) and the accounts' public pages, and answer:
1. Coordinated: the same content, posted within minutes, by accounts with little else in common.
2. Innocent look-alike: which one (breaking news, campaign, community, feed, viral post).
3. Cannot tell.

Report the counts of each answer and how often the two agreed, never the accounts. A cluster both call innocent counts as a false positive; "cannot tell" is reported separately, not dropped.

## Reporting template (one row in `PLAN.md` Results)

| When | Data (size, labels) | Core commit and flags | Precision | Recall | FPR | Notes |
|---|---|---|---|---|---|---|
| 15.11 hh:mm | name; N accounts (b bots, h humans) or unlabelled; dev or held-out | `abc1234`, rules only / `--similar-text`, cut 0.2 | | | | clusters and sizes; flagged per 1,000 (unlabelled); audit counts; seconds; credits |

## From an answer to a change in the core

| If the runs show | Likely change | Checked by |
|---|---|---|
| Bridged humans still flagged (Q1) | Member rule: a fixed floor alongside the relative cut, or a higher ratio | Subset FPR; synthetic swarms and Test A recall must not fall below their current values |
| Recall falls with history length (Q2, Q3) | Chance rate that discounts items one group shares heavily, or per popularity band | Test A at 20 and 50; `inject` at 50+ accounts |
| False alarms from one signal on real threads (Q4) | Tighten that signal only (e.g. ignore links to the thread's own news article, or very common domains) | The audited threads, then the held-out threads |
| One noisy signal hides the others (Q5) | Each signal tested on its own, then combined | Cresci thinned, Test A |
| Networks share phrases, not texts (Q6) | A phrase item (shared runs of 5 or more words) | Test R held-out half; FPR on live threads |
| Networks act in the same threads at the same time (Q6) | Thread co-activity signal | Same as above |
| Confidence bands do not match their precision (Q7) | Show the measured precision of the band, not the raw number | All labelled sets |
| Missed swarms in languages without spaces (Q8) | Character n-gram key for text items | Planted reworded swarms per language |
| Lone bots missed | None: out of scope by design (`CLAUDE.md`); report it as a limit | n/a |

Every change follows the detection rules: no language model decides, every cluster keeps its evidence, and every change is re-run on the evaluation set with the numbers in `PLAN.md`.
