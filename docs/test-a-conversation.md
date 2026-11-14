# Test A: does the core find bots in one conversation?

Written 14.11.2026 by the front-end + infrastructure role (Makeee22). First run on the core of `main` at `65e1ed1`; **rerun on `73def06`** (after the long-text rule), see [Rerun after the long-text rule](#rerun-after-the-long-text-rule-73def06). The core was run unchanged both times.

**In short (rerun):** with 3–5 comments per account the core now finds 28–73% of the bots at precision 1.000 and no false positives. With 10–20 comments per account in the same window recall falls back to 0–5%: the chance test stops passing when a large botnet is active at the same time.

## Question

Our stated use case is that "a hobbyist site owner and a large company can both check their comment sections" (`docs/core-design.md`, Intent), and the website plans to collect a site's comments with Context.dev. In a comment section or one Twitter conversation, each account has only a few comments. The headline numbers (precision 1.000, recall 0.726 on Cresci 2017) were measured on **full account timelines**, with hundreds of tweets per account. `docs/core-design.md` already warns: *"Small data proves little. With few comments the chance test rarely passes, by design."*

So: how much of the recall is left when each account has only a few comments?

## Method

- Data: Cresci 2017 converted with `python -m swarm.cresci` (6,637,615 comments, 12,737 profiles). Research use only; it stayed on the laptop. Only the aggregate numbers below leave the machine.
- Cresci has no threads, so "a conversation" is **simulated**: a time window starting 2014-10-01 (when genuine accounts and the social botnets are all active), and each account keeps only its **first N comments** in that window.
- Windows: 1, 7 and 30 days. N: 1, 3, 5, 10, 20, and all comments in the window.
- Each cut ran through `swarm.core.analyze(comments, profiles)` with the default settings (cut 0.2, rules only, no similar-text layer). Labels were read only to measure.
- Traditional spambots and fake followers are not active in these windows, so only the three social botnets take part.

## Results (first run, `65e1ed1`, before the long-text rule)

Precision / recall / false-positive rate at the default cut 0.2, counted per account.

| Window | Comments per account | Comments | Humans | Bots | Clusters | Precision | Recall | FPR |
|---|---|---|---|---|---|---|---|---|
| 1 day | 1 | 1,771 | 484 | 1,287 | 0 | n/a | 0.000 | 0.000 |
| 1 day | 3 | 5,018 | 484 | 1,287 | 0 | n/a | 0.000 | 0.000 |
| 1 day | 5 | 7,793 | 484 | 1,287 | 0 | n/a | 0.000 | 0.000 |
| 1 day | 10 | 11,927 | 484 | 1,287 | 0 | n/a | 0.000 | 0.000 |
| 1 day | 20 | 15,734 | 484 | 1,287 | 0 | n/a | 0.000 | 0.000 |
| 1 day | all | 28,164 | 484 | 1,287 | 0 | n/a | 0.000 | 0.000 |
| 7 days | 1 | 2,099 | 668 | 1,431 | 0 | n/a | 0.000 | 0.000 |
| 7 days | 3 | 6,194 | 668 | 1,431 | 0 | n/a | 0.000 | 0.000 |
| 7 days | 5 | 10,192 | 668 | 1,431 | 0 | n/a | 0.000 | 0.000 |
| 7 days | 10 | 19,832 | 668 | 1,431 | 10 | 0.925 | 0.026 | 0.004 |
| 7 days | 20 | 38,002 | 668 | 1,431 | 0 | n/a | 0.000 | 0.000 |
| 7 days | all | 233,570 | 668 | 1,431 | 4 | 0.976 | 0.280 | 0.015 |
| 30 days | 1 | 2,201 | 747 | 1,454 | 0 | n/a | 0.000 | 0.000 |
| 30 days | 3 | 6,566 | 747 | 1,454 | 0 | n/a | 0.000 | 0.000 |
| 30 days | 5 | 10,896 | 747 | 1,454 | 0 | n/a | 0.000 | 0.000 |
| 30 days | 10 | 21,571 | 747 | 1,454 | 10 | 0.841 | 0.025 | 0.009 |
| 30 days | 20 | 42,395 | 747 | 1,454 | 1 | 0.000 | 0.000 | 0.013 |
| 30 days | all | 1,204,786 | 747 | 1,454 | 5 | 1.000 | 0.421 | 0.000 |
| *Full timelines (Arde, PLAN.md Results 14.11 10:35)* | | 6,637,615 | 1,083 | 9,076 | | *1.000* | *0.726* | *0.000* |

Recall per bot family, for the rows that found anything:
- 7 days, 10 per account: social 1 1%, social 2 0%, social 3 7%
- 7 days, all: social 1 0%, social 2 0%, social 3 93%
- 30 days, 10 per account: social 1 1%, social 2 0%, social 3 7%
- 30 days, all: social 1 20%, social 2 0%, social 3 93%

At the lower cut 0.05 the picture is the same: recall stays at or below 0.052 for every row with 20 or fewer comments per account.

## Findings (first run)

1. **With 20 or fewer comments per account, the core finds almost no bots: recall 0–2.6%.** With 1, 3 or 5 comments per account it finds nothing at all, in any window.
2. **It fails safe.** It does not flag humans instead: the false-positive rate stays at or below 1.5%, and most rows flag nobody. The single cluster at 30 days / 20 per account is a false positive (FPR 0.013).
3. **Recall comes back only with long histories:** 28% with a full week, 42% with a full month, 73% with full timelines. The chance test needs many shared items per account pair, which needs many comments per account.
4. **Botnets differ.** Social 3 (93% when the window is complete) posts densely; social 1 and 2 spread their copies over a longer time, so a short window misses them.

## Limits of this test

- **No real threads.** Bots in one real conversation write about the same topic, so their copies may be denser than in a random time slice; the real numbers may be somewhat better. The gap (0–3% vs 73%) is too large for this to change the conclusion.
- **First N comments, not a random N.** Taking the first N per account is like "the account's comments in this thread so far".
- **More bots than humans** in these windows (about 2:1), unlike a real comment section.
- **One dataset from 2014.** Rules only; the similar-text layer was not run.

## What it means for the product

The core works on **account histories**, not on **one conversation**. That clashes with "check your comment section" as the main use case. Options for the team:

1. **Conversation → participants → their histories (suggested).** Collect the conversation (Context.dev), then each participant's recent posts, and run the core on those. Fits the plan, since Context.dev is already the collector, and gives an honest pitch: "give us a conversation, we examine the people in it".
2. **Change the target:** "analyse account histories and large exports" (moderators, platforms, researchers). Honest, but further from "check your comment section".
3. **Keep the target and say the limit out loud** in the pitch, with this table. Judges weigh honesty about false positives and limits.

Whatever is chosen, this table belongs in the pitch next to the 0.726: it shows exactly where the method works and where it does not.

## Rerun after the long-text rule (`73def06`)

Same data, same cuts, same script; the only change is the core (one shared text of at least 10 words can now link a pair, plus the other commits up to `73def06`).

| Comments per account | 1 day: recall (P / FPR) | 7 days: recall (P / FPR) | 30 days: recall (P / FPR) | First run, all windows |
|---|---|---|---|---|
| 1 | 0.006 (1.000 / 0.000) | 0.008 (1.000 / 0.000) | 0.008 (1.000 / 0.000) | 0.000 |
| **3** | **0.280** (1.000 / 0.000) | **0.321** (1.000 / 0.000) | **0.316** (1.000 / 0.000) | 0.000 |
| **5** | **0.647** (1.000 / 0.000) | **0.729** (1.000 / 0.000) | **0.717** (1.000 / 0.000) | 0.000 |
| **10** | **0.000** | **0.026** (0.925 / 0.004) | **0.025** (0.841 / 0.009) | 0.000–0.026 |
| **20** | **0.000** | **0.000** | **0.000** (1 false-positive cluster, FPR 0.013) | 0.000 |
| all in window | 0.000 | 0.280 (0.976 / 0.015) | 0.421 (1.000 / 0.000) | same |

Recall per family at 5 comments, 7 days: social 1 71%, social 2 0% (14 accounts), social 3 79%.

### Why more comments find fewer bots

Run at confidence 0 for the 7-day window, so the cut plays no part:

| Comments per account | Text items | Linked pairs (text) | Largest clusters (accounts) | Recall at confidence ≥ 0 |
|---|---|---|---|---|
| 5 | 8,483 | **1,606** | 538, 333, 16 | 0.740 |
| 10 | 16,707 | **118** | 5, 5, 4 | 0.052 |
| 20 | 32,395 | **64** | 6, 5, 4 | 0.027 |

The drop is in the **chance test**, not the confidence cut: with 10 or 20 comments per account it passes 118 and 64 pairs instead of 1,606. With more comments, the botnet's own copies make each shared text common, so no pair looks surprising any more. This is the known limit in `docs/core-design.md` ("Big swarms hide small evidence"), now measured: in this window the effect is large enough to hide a 538-account botnet completely.

**Why this differs from the 0.778 in `PLAN.md` (Cresci thinned to 10 comments per account):** that test picks 10 comments by hash from each account's **whole history**, so a botnet's copies are spread over years and rarely pile up. Test A takes the comments of **one window**, so the botnet's campaigns overlap, as they would in one conversation or one news cycle. Both are honest measurements of different situations; the window is closer to the product's use case.

### What it means

- **The long-text rule is a big step**: a conversation-sized sample (3–5 comments per account) now finds most of these bots, with no false positives.
- **More data must not hide a swarm.** A large, active botnet is exactly what the tool should find, and it is the case where recall falls to zero. For the backend owner to decide; ideas: limit the weight of items shared by very many accounts in the test, run the test per signal or per item size, or treat a large group sharing many long texts as evidence on its own.
- Until that is fixed, the result depends on how much data is fed in. In the product that matters for the "conversation → participants → histories" pipeline: fetching longer histories can make the result worse, not better.

The diagnosis used `analyze(..., min_confidence=0)` on the 7-day cuts; the code is in the same throwaway script as the rest of this test.

## Reproduce

Needs the Cresci 2017 zips (research use only, never committed) and `backend/requirements.txt`.

```bash
cd backend
python -m swarm.cresci ../data/raw/cresci-2017 ../data/raw/cresci-std        # the inner *.csv.zip files
```

Then, for one row (example: 7 days, 10 comments per account), cut the comments with DuckDB and run the core:

```sql
copy (
  select * exclude (rn) from (
    select *, row_number() over (partition by username order by timestamp, comment_id) as rn
    from read_csv('../data/raw/cresci-std/comments.csv', header=true, all_varchar=true)
    where timestamp >= '2014-10-01' and timestamp < '2014-10-08'
  ) where rn <= 10
) to 'cut.csv' (header);
```

```bash
python -m swarm cut.csv --profiles ../data/raw/cresci-std/profiles.csv
```

Run time on a laptop: 1–19 s per row.
