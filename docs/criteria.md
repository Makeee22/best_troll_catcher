# Detection criteria

What makes the core link, group and flag accounts, with every value and how it was chosen. The reasons and the
measurements behind each rule are in `docs/core-design.md`; every evaluation run is in `PLAN.md`, Results.
Written 15.11.2026 by the backend owner, taking over from the data owner.

**How values were chosen:** labels measure, they never train. Only the confidence cut was picked with the labels
visible as a tuning step; the other values were set before a labelled run, or (marked below) their form was settled
after one, which we declare.

## Signals: what two accounts can share

| Signal | Item | Notes |
|---|---|---|
| `text` | the same text after normalising (lower case, without links and @mentions, words only) | texts under **5 words** give no item (`min_words`) |
| `link` | the same link (scheme, `www.`, tracking parameters, fragment and trailing slash ignored) | found in `text` and `links` |
| `repost` | reposting the same post | |
| `reply` | answering the same post | **not counted** for an account whose every post is in one thread (`thread_only`): answering that thread's posts is what being in it means (handoff R7) |
| `similar_text` | reworded copies: texts whose embeddings are at least **0.9** similar (`minishlab/potion-multilingual-128M`) | optional (`--similar-text`); up to 1,000,000 texts |
| created together | two accounts created within **30 days** of each other (`created_days`) | never links on its own; it can only strengthen a content link |

## Linking two accounts

| Criterion | Value | Chosen |
|---|---|---|
| Chance test | Poisson upper bound on P(shared ≥ c) for `n1 × n2 × S` expected, per signal | design |
| Chance rate `S` | per signal; for **copied text** an item counts as if at most **10** accounts shared it (`rate_cap`), so a large botnet's own copies cannot set it. Links, reposts and replies use the true rate: many people sharing one breaking-news link, reposting one viral post or answering one popular post is normal (Test B, handoff R7) | value chosen 14.11 night **with labels visible** (3 and 5 turned the synthetic look-alikes into clusters, 10 did not); form revised 15.11 after Test B |
| False discovery rate | **1%** across all tested pairs (Benjamini-Hochberg, `alpha`) | design |
| Evidence needed | **2** shared items (`min_shared`), or **one** text of **10+ words** (`long_words`) | form settled after a labelled run (the long-text rule), declared |
| Pair budget | at most 1,000,000,000 pair rows; the widest items are left out beyond it, with a warning | resources |

## Clusters and flags

| Criterion | Value | Chosen |
|---|---|---|
| Cluster | linked accounts, at least **3** (`min_size`) | design (lone bots are out of scope, B14) |
| Confidence | each member's copied share per signal, weighted by how many of the cluster's links that signal carries; the cluster's confidence is the members' average. Not a probability | form revised after Test F (Fox8), declared |
| Reported | clusters with confidence at least **0.2** (`min_confidence`) | **the one value chosen with labels visible** |
| Flagged member | own copied share at least **0.5 ×** the cluster's confidence (`member_ratio`); the others are listed as linked, not flagged | value not tuned; the rule's form revised once after a labelled run (a fixed cut was dropped), declared |
| Declared automation | "bot", "feed", "RSS" in the name, or "bot", "RSS", "automated" in the bio ("not a bot" does not count) | a description only: never changes confidence or what is listed |

## Innocent look-alikes, each with a test

Breaking news (one link shared at once), a real campaign or fan community, one viral post reposted, a retweet storm
(thousands reposting the same few posts), a common short greeting, readers replying to a thread's top posts, and
benign automated feeds. **Known limit:** feeds posting the same wire text are coordinated by this definition and are
flagged (marked when they say they are automated).

**What a flag means:** a reason to watch an account, not a verdict (B15). Some flagged accounts are real people.
