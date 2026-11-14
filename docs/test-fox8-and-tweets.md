# Test F: Fox8-23 and a large unlabelled tweet set

Written 14.11.2026 (late evening) by J0l3s, following `docs/test-plan-broad-data.md`. Core of `main` at `284adf9`, run unchanged with default parameters (cut 0.2, `member_ratio` 0.5). Conversion scripts are outside the repo; the data and every result file are in `backend/data/` (ignored by git, checked with `git check-ignore`). This file holds aggregate numbers only: no usernames, no account ids, no comment texts.

**In short:**
- **Fox8-23** (2,279 labelled Twitter accounts, 1,140 of them bots that write with ChatGPT): precision **1.000**, recall **0.997**, FPR **0.000** at the cut 0.2, on the dev half, the held-out half and the whole set alike. The bots are found almost entirely through **reposts and replies among themselves**, not through shared text.
- **But the result hangs on the cut.** The one cluster scores confidence **0.24–0.28**, so at a cut of 0.3 recall is 0. On reposts alone the same cluster scores 0.60. Adding signals that the bots *don't* share lowers their confidence (Q5, Q7).
- **Large unlabelled tweet set** (1,000,000 accounts, 18.8M tweets, text and links only, no timestamps): on a sample of 215,930 accounts (4.1M tweets) the core flags **1.9 accounts per 1,000** in 118 clusters, almost all small (median size 3). No audit has been done yet, so this is not yet a false-positive rate (Q4).
- **Scale (Q8):** 1.7M tweets in 31 s and 1.2 GB of memory; 4.1M tweets in **17 min and 7 GB peak** on an 8 GB laptop (swapping). The full 18.8M will not fit on this laptop or on the 8 GB server as it is.

## Data

| | Fox8-23 | Tweet set (`id_tweet_part001`–`011`) |
|---|---|---|
| Source | Fox8-23 dataset (Yang & Menczer 2023, a botnet of accounts posting ChatGPT-written tweets), here already in the standard columns (`fox8_posts.csv`) | 11 zipped CSV parts; 1,000,000 accounts with ids 0–999,999 and at most 21 tweets each. The account count matches TwiBot-22's, **not confirmed** |
| Labels | `bot:fox8` 1,140, `human` 1,139 (one human has no content) | none in the data folder |
| Comments | 368,028 (median 195 per account), 2009–2023 | 18,769,592 |
| Columns with data | text, links, repost_of, parent_id, timestamp, comment_id, likes, client, language | text, links |
| Licence and terms | **to be recorded in `data/README.md` by the data owner**; treated like Cresci: research use, never committed, quoted or served | same |

### Conversion

- **Fox8:** the file had `label` (and `user_id`) on every comment. The label moved to a new `profiles.csv` (`username`, `label`); `comments.csv` keeps the standard columns from `docs/api.md`. Each account had one label.
- **Split (test plan, "Development and held-out data"):** 50/50 by a SHA-256 hash of the username, made before looking at any result. Dev: 576 bots, 556 humans. Held-out: 564 bots, 583 humans. Fox8 is one botnet, so a split by network was not possible. No core change was made, so both halves are measurements and nothing was tuned on dev.
- **Tweets:** already `username,text,links`; the parts were joined without their repeated headers. **Mistake to note:** the join command skipped parts 002–009 (bash 3.2 does not zero-pad `{02..11}`), so the run covers parts 001, 010 and 011: 4,091,147 tweets from 215,930 whole accounts (22% of accounts). It is a fair sample of accounts, not of time. Because the full set does not fit in memory anyway (see Scale), it was not re-run.

## Results

### Fox8-23, rules only (`python -m swarm comments.csv --profiles profiles.csv`)

| Data | Precision | Recall | FPR | Cluster | Seconds / peak memory |
|---|---|---|---|---|---|
| Whole set (2,279) | 1.000 | 0.997 (1,137 of 1,140) | 0.000 (0 of 1,138) | 1: 1,138 accounts, 1,137 flagged, confidence 0.275 | 10 s / 0.8 GB |
| Dev half (1,132) | 1.000 | 0.997 | 0.000 | 1: 575 accounts, 574 flagged, confidence 0.239 | 5 s / 0.4 GB |
| **Held-out half** (1,147) | 1.000 | 0.993 | 0.000 | 1: 562 accounts, 560 flagged, confidence 0.240 | 5 s / 0.4 GB |
| Dev, `--similar-text` | 1.000 | 0.997 | 0.000 | confidence 0.243; 1,546 similar-text items, 124 links | 28 s / 2.1 GB |
| Held-out, `--similar-text` | 1.000 | 0.993 | 0.000 | confidence 0.244; 1,460 items, 56 links | 23 s / 2.1 GB |

**By cut (Q7)**, whole set (held-out in brackets):

| Cut | 0 | 0.05 | 0.1 | 0.2 | 0.3 | 0.5 |
|---|---|---|---|---|---|---|
| Recall | 0.997 (0.993) | 0.997 (0.993) | 0.997 (0.993) | 0.997 (0.993) | **0** (0) | 0 (0) |
| FPR | 0.014 (0.012) | 0.007 (0.003) | 0 (0) | 0 (0) | 0 (0) | 0 (0) |

The cut 0.2 was chosen on Cresci with labels visible, not on Fox8; on Fox8 it happens to sit just under the botnet's confidence. A dashboard reading "confidence 0.27" for a cluster that is 100% bots shows that **the number is not a probability** (it is the members' average copied share). Members' `copied_share`, deciles: 0.12, 0.21, 0.23, 0.25, 0.26, 0.27, 0.28, 0.29, 0.31, 0.34, max 0.56.

**Evidence:** of the 500 strongest edges, 460 are `repost` and 40 `reply`; the top 20 items are 13 reposts and 7 replies. Median `copy_gap_seconds` is about 14 hours (51,753 s over 17,309 items): the bots repost each other slowly, not in bursts.

**One signal at a time (Q5)**, dev half, other columns removed (cut 0.2; the `text` run also uses URLs found in the text):

| Signals | Recall at 0.2 | FPR | Cluster confidence | Recall at 0.1 |
|---|---|---|---|---|
| repost only | **0.993** | 0 | **0.604** | 0.993 |
| reply only | 0.670 | 0 | 0.515 | 0.670 |
| link only | 0.297 | 0 | 0.228 | 0.297 |
| text (+ links in text) | **0** | 0 | under 0.2 | 0.991 |
| all but repost | 0.995 | 0 | 0.252 | 0.995 |
| all | 0.997 | 0 | 0.239 | 0.997 |

So text (ChatGPT-written, never copied word for word) adds hundreds of thousands of unshared items to each bot's own content, which halves the confidence (0.60 to 0.24) without adding recall. This is the test plan's "one noisy signal hides the others", measured on real data: the confidence of a cluster falls as the bots post more of their own unshared content.

### Tweet set, rules only (no labels)

| Sample | Comments / accounts | Clusters | Flagged (linked) | Flagged per 1,000 | Seconds / peak memory |
|---|---|---|---|---|---|
| Part 001 | 1,747,003 / 86,865 | 20 (sizes 3–70) | 118 (156) | 1.36 | 31 s / 1.2 GB |
| Parts 001, 010, 011 | 4,091,147 / 215,930 | 118 (median size 3; one of 71, next 18) | 413 (543) | 1.91 | 1,032 s / 7.0 GB |

- Signals: only `text` and `link` could run (no `repost_of`, `parent_id` or timestamps). Clusters linked mainly by text: 108; by links: 10. No cluster's members say they are automated (but the file has no names or bios, so the mark cannot work here).
- Confidence bands: 0.2–0.4: 76 clusters, 0.4–0.6: 26, 0.6–0.8: 12, 0.8–1.0: 4.
- Without timestamps there is no `copy_gap_seconds`, so "posted within minutes" cannot be checked from the result.
- **Flagged per 1,000 is not an FPR.** It is an upper bound on false alarms until the clusters are audited (test plan, "Auditing a flagged cluster"). If the set is TwiBot-22, its own labels would give a real FPR and recall: see Next steps.

### Planted swarms on the tweet background (`swarm.inject`)

**Simulated** swarms planted one at a time into part 001 (86,865 real accounts, 1.7M tweets), rules only, seed 0, 20 scenarios in 553 s. Columns: swarm size, copied messages, own posts per member, share of members posting each message, words per message, variant.

| Planted swarm (simulated) | Found | Confidence |
|---|---|---|
| 3, 5, 8, 20 and **50** accounts, 6 messages of 15 words, 10 own posts | all members | 0.375 |
| 8 accounts, 1 or 2 messages among 10 own posts | 0 of 8 | – |
| 8 accounts, 3 messages / 20 messages | 8 of 8 | 0.231 / 0.667 |
| 8 accounts, 6 messages, 0 own posts | 8 of 8 | 1.000 |
| 8 accounts, 6 messages, 30, 100 or 300 own posts | 0 of 8 | – |
| Half / a quarter of members post each message | 6 of 8 / 3 of 8 | 0.223 / 0.206 |
| Edited or reworded copies | 0 of 8 | – |
| One 15-word message, 0 / 2 own posts | 8 of 8 | 1.000 / 0.333 |
| One 7-word message, 2 own posts | 0 of 8 | – |

The background's own 118 flagged accounts stay the same in every scenario: a planted swarm neither pulls real accounts in nor hides them. The **50-account swarm is found here**, while it was missed on the small Reddit background (14.11 16:30): with 86,865 background accounts its copies are rare enough to beat the chance rate, which supports the "large swarm hides itself in a small background" explanation (Q3). The limits match the earlier runs: 30 or more own posts per member, or rewording without `--similar-text`, still hide a swarm.

## What it means for the questions in the test plan

- **Q1 (member rule):** Fox8 gives no evidence either way: no human is linked to the botnet at 0.2, so the member rule never decides anything. At cut 0, 16 humans are flagged; a fixed own-share cut of 0.5 would also have dropped almost every bot (90% of the bots' shares are under 0.34, the highest is 0.56).
- **Q5 (signals on their own):** **yes, a noisy signal hides the others.** On Fox8, testing reposts alone gives a confidence of 0.60 instead of 0.24. Taking each signal's confidence on its own (or the best of them) would keep this botnet well above the cut; it has to be checked against the Cresci subset's bridged humans before adopting it.
- **Q6 (what today's bots share):** a ChatGPT-written botnet shares no text, as Test R suggested, but it **amplifies itself**: reposts and replies between members. The repost and reply signals matter more than text for this kind of network. The website's collectors should keep `repost_of` and `parent_id` wherever the platform has them.
- **Q7 (is the confidence honest):** no. A cluster that is 100% bots scores 0.24–0.28. The dashboard should not present it as a probability. Showing the measured precision per band, or a band name, is safer.
- **Q8 (scale):** memory, not CPU, is the limit. Between 1.7M and 4.1M comments the time grew 33-fold (31 s to 17 min) because the laptop ran out of memory. The 8 GB server needs a job limit around 2–3 million comments, or the core needs to process in chunks.
- **Q3 (large botnet hides itself):** a planted 50-account swarm is found in a background of 86,865 accounts but was missed in a background of 26. The background's size matters as much as the swarm's.
- **Q4 (false positives on unlabelled data):** 1.9 flagged per 1,000 accounts is a starting point. The audit is still to do.

## Limits

- Fox8's humans may not come from the same community as the bots (how they were sampled is to be checked in the paper). If they don't, an FPR of 0 is easy and says little about bridged humans (the Cresci subset problem).
- Fox8 is one botnet. A split by account cannot test whether the result carries to a different network.
- The tweet set has no labels here, no timestamps and only two signals; 22% of its accounts were run.
- One run each; the core is deterministic, so repeating gives the same numbers.

## Next steps

1. **Data owner (TheSnowman99):** record the source and licence of both sets in `data/README.md`; confirm whether the tweet set is TwiBot-22 and whether its `label.csv` maps onto ids 0–999,999. With labels it answers Q1, Q5 and Q7 on a million accounts.
2. **Two people audit** the 16 tweet-set clusters at confidence 0.6 or more (counts only, never accounts).
3. **Backend (Arde1001):** decide on Q5 (per-signal confidence) with Fox8 dev as evidence, then rerun Fox8 held-out once, the Cresci subset and Test A; and a size limit for server jobs (Q8).
4. Rerun the whole tweet set on a machine with 16 GB or more, or in chunks, after the join is fixed (`seq -w 2 11`).

## Test F2: `arde/group-test`

Run 15.11.2026 00:00–00:35 by J0l3s on the same data and halves as above. Branch `arde/group-test` at **`8600aa2`**, which builds on `arde/link-kinds` (`5e5fef7`) and adds: confidence as each kind's copied share **weighted by the cluster's links of that kind**; a **rate cap** (an item counts toward the chance rate as if at most 10 accounts shared it); and a **group test** (`signals.group_test`, off with `--no-group-test`). Rules only, cut 0.2, tests pass (218). Aggregate numbers only. The Fox8 held-out half was run once, after the dev half looked right.

### The three versions on the same runs

| Run | `main` (`284adf9`, Test F) | `arde/link-kinds` (`5e5fef7`) | `arde/group-test` (`8600aa2`) |
|---|---|---|---|
| Fox8 dev: cluster confidence | 0.239 | 0.239 | **0.565** (0.565 with `--no-group-test`) |
| Fox8 dev: flagged members / recall at 0.2 | 574 of 575 / 0.997 | 574 of 575 / 0.997 | 575 of 575 / 0.998 |
| Fox8 dev: recall at 0.3 and 0.5 | **0** | **0** | **0.998** |
| Fox8 dev: FPR at 0 / 0.05 / 0.1 / 0.2+ | 0.025 / 0 / 0 / 0 | 0.011 / 0.007 / 0.007 / 0 | **0.104** / 0.077 / 0 / 0 |
| Fox8 **held-out**: confidence; recall at 0.2–0.5 | 0.240; 0.993 at 0.2, 0 at 0.3+ | not run | **0.561; 0.997 at every cut** |
| Fox8 held-out: FPR at 0 / 0.05 / 0.1 / 0.2+ | 0.012 / 0.003 / 0 / 0 | not run | **0.127 / 0.088 / 0.052** / 0 |
| Tweets part 001: clusters; flagged per 1,000 | 20; 1.36 | 35; 1.91 | 38; **2.00** |
| Tweets part 001: bands 0.2–0.4 / 0.4–0.6 / 0.6–0.8 / 0.8–1.0 | 14 / 4 / 0 / 2 | 26 / 6 / 1 / 2 | 29 / 6 / 1 / 2 |
| Tweets part 001: seconds / peak memory | 31 s / 1.2 GB | 70 s / 2.1 GB | 42 s / 2.5 GB (`SWARM_MEMORY_LIMIT=4GB`) |
| Planted swarms on part 001: found | as in Test F | identical | **identical** (every scenario, same confidence) |
| Planted swarms: real accounts flagged underneath | 118 | 166 | 174 |
| Tweets 4.1M: clusters; flagged per 1,000 | 118; 1.91 | 169; 2.71 | 176; **2.83** |
| Tweets 4.1M: bands | 76 / 26 / 12 / 4 | 102 / 41 / 15 / 11 | 108 / 42 / 15 / 11 |
| Tweets 4.1M: seconds / peak memory | 1,032 s / 7.0 GB (swapping) | 264 s / 4.5 GB (4 GB cap) | **443 s / 9.9 GB** (4 GB cap) |

Flagged per 1,000 on the tweet set is **not a false-positive rate**: none of these clusters has been audited.

### Group test

| Run | Groups tested | Accepted | Links added |
|---|---|---|---|
| Fox8 dev | 7 | 1 | 261 |
| Fox8 held-out | 16 | 1 | 26 |
| Tweets part 001 | 412 | 79 | 0 |
| Tweets 4.1M | 699 | 181 | 0 |

### What it shows

- **The Fox8 fix works.** The botnet's confidence goes from 0.24 to 0.56–0.57 on both halves, so recall no longer collapses at 0.3 or 0.5. On the held-out half recall is 0.997 at every cut, with no human flagged at 0.2 or above.
- **The confidence change does all of it; the group test adds nothing measurable here.** With and without `--no-group-test` the Fox8 dev results are identical. Its 261 links (dev) and 26 (held-out) join pairs that were already in the cluster. On the tweet set it accepts groups but adds no links. The rate cap roughly doubles the repost and reply links on Fox8 (dev repost links 75,039 to 136,692) without changing who is flagged at 0.2.
- **More humans below the cut.** Humans who form their own small clusters now score higher. On Fox8 the FPR at cuts 0–0.1 rose from about 0.01–0.03 to 0.05–0.13 (held-out at 0.1: 30 of 583 humans; main had 0). At the cut the product uses (0.2) it is still 0 on both halves. Lowering the cut under 0.2 would now cost much more than before.
- **The tweet set flags a little more.** Per 1,000 accounts: part 001 1.36 → 1.91 → 2.00; the 4.1M sample 1.91 → 2.71 → 2.83 (+48% against `main`, +4% against `link-kinds`). Almost all the rise came with `link-kinds`. Under team decision B15 (find more, accept some false positives) that is within the agreed direction, but it is unaudited: how many of the extra clusters are real is not known.
- **The memory cap is not holding on this branch.** The 4.1M sample peaked at **9.9 GB** of process memory with `SWARM_MEMORY_LIMIT=4GB`, against 4.5 GB on `link-kinds`, and took 443 s against 264 s. The cap only bounds DuckDB, so the extra memory is probably used outside it (the group test or the weighted share). The planted-swarm run also took longer (1,318 s against 717 s). On the 8 GB server this size of input would swap again; **for the backend owner to check before merging.**
