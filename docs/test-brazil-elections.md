# Test B: Brazil elections 2021 (retweets and replies, no text)

Written 15.11.2026 (night) by J0l3s. Runs on `main` twice: first with the core as of `85e4838` (Test F's detection plus the DuckDB memory cap), then with the new core of `64bc287` (link-weighted confidence, chance rate cap 10, R7 reply rule; detection unchanged up to `1d76806`). Conversion scripts are outside the repo; data and results are in `backend/data/` (ignored by git). This file holds aggregate numbers only: no account ids, no tweet ids, no texts (the data has none).

**In short:**
- A year of Brazilian election Twitter (57.8M tweets, 3.2M accounts) with **no text**: only who retweeted, quoted or replied to what, and when. Only the `repost` and `reply` signals can run.
- **It does not fit the laptop.** A single month (4.6M tweets) ran out of memory and temporary disk on the old core, whole or split in half: retweets of viral posts make 2.3 billion account pairs.
- On one day (1 September, 75,805 accounts) the **old core found nothing** (0 links), and the **new core flagged 266 of every 1,000 accounts**, mostly in one cluster of 19,987 accounts at confidence 0.975.
- The flagged accounts are **not** enriched in high bot scores (6.4% against 7.4% of all accounts that day). The cluster is people who retweeted the same viral posts: the "one viral post" look-alike the design must rule out. The cause is the new chance rate cap. **The current core should not be run on retweet-heavy data until this is fixed.**

## Data

| | |
|---|---|
| Files | `backend/data/Brazil_elections_2021_csv/`: 343 daily files `electionsYYYY-MM-DD.csv.gz`, 1 January – 31 December 2021, 1.1 GB compressed |
| Columns | `id_str`, `user.id_str`, `timestamp_ms`, `retweeted_status.id_str`, `quoted_status.id_str`, `in_reply_to_status_id_str`, `botscore`; all ids are numbers, no usernames, no text |
| Size | 57,752,393 rows (57,585,583 distinct tweets), 3,186,875 accounts; median 2 tweets per account, 99th percentile 310, maximum 26,772 |
| Kinds | 35.0M retweets, 8.1M quotes, 17.2M replies |
| `botscore` | 0–1 on every tweet, from a bot-detection model (not stated which); it varies between an account's tweets for 1.5M accounts. Account average ≥ 0.5: 12.2% of accounts |
| Source and licence | **not recorded**: for the data owner to add to `data/README.md`. Treated like Cresci: research use, never committed, quoted or served |

### Conversion to the standard format (`docs/api.md`)

| Standard column | From |
|---|---|
| `username` | `user.id_str` |
| `comment_id` | `id_str` (duplicates dropped) |
| `timestamp` | `timestamp_ms`, as ISO 8601 UTC |
| `repost_of` | `retweeted_status.id_str` |
| `parent_id` | `in_reply_to_status_id_str` |
| `label` (profiles) | `bot:botscore` when the account's average `botscore` over the window is 0.5 or more, else `human` |

Quotes were left out (the standard format has no column for them). **The labels are weak:** they are another model's opinion, not ground truth, so "precision" below means agreement with that model. The 0.5 threshold is the usual midpoint and was not tuned. The month was split 50/50 by a hash of the account before any run.

## What was run

### September 2021, whole and halves

4,574,359 tweets, 669,208 accounts (62,334 with average score ≥ 0.5, 9.3%); dev half 334,511 accounts, held-out 334,697.

| Run | Core | Result | Time / peak |
|---|---|---|---|
| Whole month | `85e4838` | **Out of memory**: DuckDB filled 15.6 GB of temporary disk | 305 s / 4.45 GB |
| Dev half | `85e4838` | **Out of memory** (23.0 GB temporary) | 191 s / 4.45 GB |
| Held-out half | `85e4838` | **Out of memory** (21.5 GB temporary) | 150 s / 4.46 GB |

Why: 189,007 retweeted tweets, the widest retweeted by 15,838 accounts. Every pair of accounts that share an item is a row before the chance test: 2.29 billion pairs for the month. The core's pair budget (1 billion) leaves out only the widest items once that is exceeded, and even 1 billion pairs does not fit in 8 GB of memory plus the free disk. The memory cap works (peak 4.45 GB, no swapping); the disk runs out instead.

### Smaller windows

| Window | Tweets | Accounts | Widest item | Account pairs sharing an item |
|---|---|---|---|---|
| 1 September | 181,929 | 75,805 (5,591 weak bots) | 9,811 | 138M |
| 7 September (protest day) | 499,241 | 189,367 | 13,892 | 449M |
| 1–7 September | 1,717,096 | 369,547 | 15,119 | 1.36 billion |
| 22–28 September | 845,156 | 211,837 (19,352 weak bots) | 7,061 | 347M |

### 1 September, old and new core

| | Old core (`85e4838`) | New core (`64bc287`) |
|---|---|---|
| Linked pairs (repost / reply) | 0 / 0 | **11,172,279** / 143,252 |
| Clusters | 0 | 46: **19,987 accounts** (19,917 flagged) at 0.975, then 37 at 0.959, 10 at 1.000, … |
| Confidence bands 0.6–0.8 / 0.8–1.0 | – | 8 / 38 (none under 0.6) |
| Flagged accounts | 0 | **20,129 = 266 per 1,000** |
| Against the weak labels | – | precision 0.064, recall 0.250, FPR 0.287, **the same at every cut 0–0.5** |
| Time / peak memory | 201 s / 4.55 GB | **688 s** / 4.63 GB |

The new result's `diagnostics`: of 105.0M account pairs that shared a repost, 11.17M shared enough to test and **every one of them was linked**. The widest items are reposts shared by 9,811, 8,598 and 4,135 accounts.

The 22–28 September week was started on the new core and stopped on request before it finished; it was not rerun.

## What it means

- **The rate cap turns viral retweets into evidence.** `rate_cap` counts each item as if at most 10 accounts shared it, so that a large botnet cannot raise the chance rate it is tested against (it is what lifts Fox8 from 0.24 to 0.58). On real retweet data it also lowers the chance rate for posts retweeted by thousands, so any two accounts that retweeted two of the same viral posts beat chance. Millions of such pairs chain into one cluster.
- **The flagged accounts look like everyone else.** 6.4% of them have a high bot score against 7.4% of all accounts that day: the cluster is not a bot network by the only other measure available. Its confidence (0.975) is high because these accounts posted little else that day, so the cut cannot remove it.
- **This is a false-positive problem the judges will look for.** A retweet storm around a news event is exactly the "breaking news / one viral post" look-alike. Before the cap the core handled it correctly (nothing linked).
- **Scale:** retweet data grows with the square of an item's audience. At about 140M candidate pairs a run takes 3–11 minutes and 4.6 GB; at a billion it does not finish on 8 GB. The server needs a pair limit far below the current 1 billion, or a different way to handle very wide items.

## Suggested changes (for the backend owner)

1. Apply `rate_cap` only up to a ceiling of sharers, or not to `repost` items shared by more than some hundreds of accounts; or keep the uncapped rate for reposts, as R7 already does for replies. Check on this day (expect close to 0 flagged) and on Fox8 (expect confidence near 0.58 to hold).
2. A lower pair budget for server jobs (Q8), with the warning the core already gives when items are left out.
3. Whatever is chosen, rerun 1 September and 22–28 September once, and the dev and held-out halves if memory allows.

## Limits

- Weak labels from another model; no ground truth.
- No text, so only two signals; quotes not used.
- One day measured on the new core; the week was stopped.
