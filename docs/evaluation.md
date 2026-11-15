# Evaluation

How well the core finds coordinated accounts, how that was measured, and how each change to the method moved the
numbers. The datasets, their sources and terms are in [`data/README.md`](../data/README.md); none of them is shared
here, only aggregate numbers. The method is in [`core-design.md`](core-design.md), the criteria in
[`criteria.md`](criteria.md).

## How we measure

- **Per account.** Recall is the share of labelled bots that are flagged; the false-positive rate (FPR) is the share
  of labelled humans flagged; precision is the share of flagged accounts that are bots. A flagged account is a flagged
  member of a listed cluster (`docs/api.md`, "Metrics").
- **Labels measure, they never train.** The confidence cut (0.2) is the one value chosen with the labels visible.
- **Held-out data** where we had enough: Fox8-23 was split 50/50 by a hash of the username before any run, and the
  held-out half was run once per change.
- **Planted swarms** (`python -m swarm.inject`) are simulated accounts added to a real background; they are labelled as
  simulated, and the background accounts are assumed not to be coordinated.

## Results on the final core

Rules only (no similar-text layer), default settings, cut 0.2.

| Data | Precision | Recall | FPR |
|---|---|---|---|
| Cresci 2017, full (9,076 bots, 1,083 humans, 6.6M tweets) | 1.000 | 0.828 | 0.001 (1 human) |
| Cresci 2017, humans only | n/a | n/a | 0 of 1,083 flagged |
| Cresci 2017 thinned to 10 / 3 comments per account | 1.000 / 1.000 | 0.719 / 0.347 | 0 / 0 |
| Test A: Cresci as one conversation, 7 days, 10 comments per account | 0.996 | 0.911 | 0.008 |
| Test A, same window, 25 / 50 comments per account | 0.997 / 0.986 | 0.660 / 0.502 | 0.005 / 0.015 |
| Cresci subset: 377 humans next to 4,528 bots (the false-positive trap)\* | 1.000 | 0.987 | 0.000 |
| Fox8-23, held-out half\* | 1.000 | 0.997 | 0.000 |
| Community-reported Reddit bots, 2026 (Test R)\* | 0.909 | 0.139 | 0.010 |

\* Measured by teammates on the core just before the last change (the rate cap limited to copied text, 15.11); on our
own sets that change moved Cresci full from 0.833 to 0.828 and left every other number identical.

## How each change moved the numbers

| Change (14–15.11.2026) | Effect |
|---|---|
| First core: pairs tested against chance, clusters, confidence = copied share | Cresci full recall 0.726, FPR 0. Without the confidence cut: precision 0.978, 14.1% of humans flagged, which is why the cut exists |
| **Long-text rule:** one shared text of 10+ words can link a pair if it beats chance | Cresci full 0.726 → 0.790; thinned to 10 per account 0.118 → 0.778; thinned to 3: 0.018 → 0.350; FPR still 0 |
| **Unbiased chance rate:** a post never matches itself when the rate is estimated | Test A at 10 comments per account: 0.000–0.026 → 0.848–0.940 |
| **Member-level flags:** a member is flagged only when its own copied share is at least half its cluster's confidence | Cresci subset FPR 0.706 → 0.281 (266 → 106 humans flagged) |
| **Confidence weighted by the kinds that link the cluster**, and the **rate cap** (an item counts as if at most 10 accounts shared it) | Fox8 confidence 0.24 → 0.58, so recall at cuts 0.3 and 0.5 went from 0 to 0.997; Cresci subset FPR 0.281 → 0.000; Test A at 25 per account 0.076 → 0.660; Cresci full 0.766 → 0.833 |
| **Thread-only rule:** an account seen in one thread only drops its replies before pairing | A real Hacker News thread where 7 ordinary readers were flagged: 0 flagged; every labelled set unchanged |
| **Rate cap for copied text only:** links, reposts and replies keep the true rate | On real retweet data (one day of a national election, 75,805 accounts) the capped version flagged 266 of every 1,000 accounts, people who retweeted the same viral posts, while the uncapped rate linked none. Cresci full 0.833 → 0.828; everything else identical |

## The tests

**Cresci 2017, full and thinned.** The main benchmark: three social spambot families, traditional spambots and fake
followers next to genuine accounts. Thinning (each account's comments picked by hash) imitates a scraped comment
section, where each account has only a few comments.

**Test A: one conversation.** Cresci has no threads, so a conversation is simulated: a 1-, 7- or 30-day window
starting 2014-10-01, each account keeping its first N comments in it (N = 3 to 50). Recall depends on how many
comments each account has: a large, very active botnet's own copies otherwise make copying look common, which the
rate cap counters.

**The Cresci subset: the false-positive trap.** 377 humans whose communities are tied to 4,528 social bots by a few
shared posts. Before member flags, the humans inherited the botnet's confidence (FPR 0.706). Now none is flagged,
though they still sit in the botnet's cluster as linked, not flagged.

**Fox8-23 (Test F).** A 2023 botnet of accounts posting ChatGPT-written tweets, linked mostly by reposts. At first
its cluster scored 0.24, because its members also write text nobody copies; weighting the confidence by the kinds that
link the cluster lifted it to 0.58, held on the held-out half (recall 0.997, FPR 0 at 0.2 and above). Below the cut
the cost shows: at cuts 0–0.1 up to 18% of the humans would be flagged, so the cut stays at 0.2. Peak memory 0.4 GB
per half.

**Test R: community-reported Reddit bots (2026).** 72 accounts that Reddit users reported as bots and 96 background
accounts from the same threads, newest 25 comments each. 10 of the 72 were found, all from one network that pastes
the same short texts; most reported accounts share no identical text, so recall is low. The one flagged background
account is probably an unreported member.

**Planted swarms.** Into Cresci's 1,083 humans, a real Reddit thread, a Mastodon thread, a Discourse topic and a
YouTube video's comments: swarms of 3 to 50 accounts that copy 6 messages among 10 of their own posts are found in
full; at most 2 real accounts were flagged alongside. Missed by design: 1 or 2 copied messages, 30 or more own posts
per copy, edited or reworded copies (reworded ones are found with `--similar-text`).

**An unlabelled tweet set** (215,930 accounts, 4.1M tweets) checks scale: 1.9–2.8 flagged per 1,000 accounts across
versions, unaudited, so not a false-positive rate.

**IRA troll tweets, random sample.** 0 clusters: a random sample leaves about 6 tweets per account over 9 months.
A fair test needs a time window of the full files.

**Live threads** (unlabelled, counts only): Hacker News, Bluesky, Reddit, Mastodon, Discourse, YouTube, XenForo and
Invision pages ran end to end. On YouTube, clusters of single-comment accounts posting the same 10–20-word text are
found; they match known comment-copying bots but are unaudited.

## Tried and not adopted

| Idea | Why not |
|---|---|
| A model-free near-duplicate signal (word overlap, MinHash) | its many weak pairs made the shared chance test stricter: thinned recall 0.778 → 0.129 |
| Re-estimating the chance rate without the accounts already found | 879 of 1,083 Cresci humans flagged |
| Reporting clusters also by their share of copied text | +0.010 recall for 4 humans flagged; makes the cut meaningless for text-only data |
| Splitting clusters by label propagation | recall 0.726 → 0.714; the largest cluster still mixed families |
| A fixed cut on a member's own copied share | dropped every swarm that also posts its own comments; replaced by the relative member rule |
| A fixed floor of 0.3 for members | cost Fox8 recall (its bots' shares are 0.12–0.56) |
| A group-level test (whole groups denser than chance) | no measurable gain on Fox8, Test A or Cresci; it held every loosely linked pair in memory |
| A "same-thread burst" signal for raids | on Cresci, accounts replying to the same posts within minutes again and again were people in conversation (142 human pairs, 0 bot pairs) |

The known limits are in the [README](../README.md#how-well-it-works) and in `core-design.md`.
