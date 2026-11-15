# Core design (part 1)

Status: implemented in `backend/swarm/` (14–15.11.2026). The measurements behind each choice are in `docs/evaluation.md`; every criterion and its value in `docs/criteria.md`.

## Intent

An open-source program that anyone can download and run on their own data. It reads a CSV of comments, and optionally a CSV of profiles, and returns the groups of accounts that behave like one actor, each with a confidence and the evidence for it.

It exists so that a hobbyist site owner and a large company can both check their comment sections without accounts, subscriptions or a language model. The website (part 2) runs this same program on Hostinger and adds partner tools on top.

## Goals, non-goals, anti-goals

**Goals**
- One input format for any website. Every column except `username` may be missing.
- Purely algorithmic and repeatable: the same input always gives the same output.
- Thresholds that follow the data, not constants tuned to one site.
- Scales with the hardware: a laptop for small data, a server for large.
- Every reported cluster shows why it was reported.
- Measured precision, recall and false-positive rate on labelled data.

**Non-goals** (part 1)
- Lone bots. A group is at least three accounts.
- Collecting comments from a website. Part 2 does that (Context.dev).
- Explaining clusters in prose. Part 2 does that (a language model).
- Uploading data through the website. Part 2 adds that endpoint.
- Live or streaming input. The core analyses one file per run.

**Anti-goals** (would make it a failure even if it runs)
- Flagging ordinary people who shared one viral post or one piece of breaking news.
- A classifier trained on our labelled dataset. See [Evaluation](#evaluation).
- Numbers shown without saying what they were measured on.

## Constraints

- Python 3.12 or newer. One new dependency: DuckDB. FastAPI and uvicorn stay for the API.
- No network access at run time. The optional similar-text layer downloads a model once.
- The Cresci 2017 dataset is research-only and holds real people's tweets. It never enters git, the Docker image or the live site. Only aggregate numbers leave the machine.
- Simulated data is always marked as synthetic, in the data and in the output.

## Approaches considered

| | A. Similarity network | B. Behaviour fingerprint | C. Per-account features |
|---|---|---|---|
| How | Link pairs of accounts that share content more often than chance predicts. Report the linked groups. | Encode each account's timeline as a string of action types. Find groups with long identical stretches (Cresci's "digital DNA"). | Compute features per account, then cluster or classify. |
| For | The mainstream method in the literature. Matches our data. Every link is evidence a person can read. | Needs no text. Reported precision 0.98 on our dataset. | Catches lone bots. |
| Against | Reworded copies need an extra layer. | Needs long timelines and several action types, which a comment section lacks. | Learns the quirks of the training data. Similar features are not evidence of coordination. |

**Picked: A**, by the team on 14.11. C fails on the known weakness of bot benchmarks (see Evaluation). B does not fit comment sections.

## What the data showed

Before fixing the method I measured it on Cresci 2017, converted to the input format below: 6,637,615 comments from 10,159 labelled accounts with usable content (1,083 human, 9,076 bot in five families). The scripts were throwaway; the numbers are not the product's yet.

1. **Text reuse separates bots from humans.** In the three social botnets, 64–93% of tweets repeat a text that another account also posted. Among humans it is 3.5%.
2. **Timing does not.** The copies come hours apart (median 77 minutes to 25 hours). A 60-second window, the old skeleton's rule, misses most of them and matches ordinary people retweeting the same post.
3. **A chance test removes most accidental links.** Of the human pairs that share at least three texts, 19 of 748 remain after the test. Of the bot pairs, 96–98% remain.
4. **Real communities still get linked.** One group of 122 humans stays linked through shared retweets and replies. Their shared content is 5% of what they post. For bot groups it is 16–97%. That share became the confidence.
5. **Creation-date bursts are real but not yet safe to score.** About 60% of two botnets were created in one month. A naive burst score raised small human groups too, because any group of three has a third of its members in one window. It lowered precision, so in part 1 it is shown as evidence and does not change the confidence.

Result of the rule below on this data:

| Confidence cut | Precision | Humans flagged | Bots found |
|---|---|---|---|
| none | 0.978 | 14.1% (153 of 1,083) | 73.6% |
| 0.05 | 0.9994 | 0.4% (4) | 73.6% |
| **0.2 (default)** | 1.000 | 0 | 72.6% |
| 0.5 | 1.000 | 0 | 71.0% |

Bots found per family at 0.2: social 1 95%, social 2 100%, social 3 95%, traditional 47%, fake followers 41%.

How to read this honestly:
- The default cut of 0.2 was chosen while looking at these labels, so the row at 0.2 is optimistic. That is why the whole curve is reported.
- These bots copy text word for word, and the humans were collected separately from them. A modern swarm that rewords its messages would do worse.
- Traditional spambots and fake followers mostly do not act as a group. Missing half of them is expected, not a bug.
- The whole run took about one minute on an 8-core laptop.

## Input format

Two CSV files with a header row. Column names are matched without regard to case or surrounding spaces. Unknown columns are ignored with a warning. Empty cells mean "unknown".

### `comments.csv`

| Column | Used for | If missing |
|---|---|---|
| `username` | The account. **Required.** | The run stops with an error. |
| `text` | Signals `text` and `link` | Those signals are skipped. |
| `links` | Signal `link`. URLs separated by spaces. URLs inside `text` are found automatically. | Only URLs inside `text` are used. |
| `repost_of` | Signal `repost`: the id of the reposted comment | Signal skipped. |
| `parent_id` | Signal `reply`: the id of the comment this one answers | Signal skipped. |
| `timestamp` | First and last time seen, in the evidence. ISO 8601; without an offset it is read as UTC. | Times are empty in the output. |
| `comment_id` | Pointing to example comments | Row numbers are used. |
| `synthetic` | `1` or `true` marks simulated data | Treated as real data. |
| `thread_id`, `likes`, `client`, `language` | Accepted, not used yet | Nothing. |

### `profiles.csv` (optional)

| Column | Used for | If missing |
|---|---|---|
| `username` | Joining to comments. **Required in this file.** | The file is ignored with a warning. |
| `created_at` | Evidence line (how many of a cluster's accounts were created within 30 days of each other) and one more item in the chance test (see "Created together") | The line and the item are left out. |
| `label` | Measuring. `human`, `bot`, or `bot:<family>`. Anything not starting with `bot` counts as not a bot. | No metrics. |
| `display_name`, `bio`, `followers`, `following`, `post_count`, `default_avatar`, `verified`, `location`, `ip_hash`, `user_agent_hash`, `email_domain` | Accepted, not used yet | Nothing. |

`ip_hash`, `user_agent_hash` and `email_domain` are for site owners. They must be hashed before they reach the file, and the core never writes them to its output.

### What is truly required

- `username`, and
- at least one of `text`, `links`, `repost_of`, `parent_id`.

Without `username` there are no accounts to group. Without any of the four content columns there is nothing two accounts can share. In both cases the run stops and says which columns it needs. Everything else, including `timestamp` and the whole profile file, only adds evidence.

## Method

1. **Load** both files into DuckDB. Count and report rows it had to drop (no username) and values it could not read (bad timestamps).
2. **Reduce each comment to what it can share with a copy**, called items:
   - `repost`: the reposted comment's id. A repost gives only this item, since its text and links are not its own.
   - `text`: the text in lower case, without URLs and @mentions, as words only. Kept if it has at least 5 words, in any script.
   - `link`: each URL, without trailing punctuation.
   - `reply`: the parent comment's id.
3. **Count** how many accounts have each item, and how many items each account has, per signal.
4. **Pair** accounts that share an item. For each pair and signal: the number of different items they share.
5. **Test against chance.** If accounts picked items at random, with popular items picked more often, a pair with `n1` and `n2` items would share about `n1 × n2 × S` of them, where `S` is the chance that two different posts of that signal are the same item (counted over pairs of different posts, so a post never matches itself), which measures how concentrated the signal is on popular items. The test asks how likely the real count is under that assumption. A viral post raises `S`, so sharing it proves little. The cut-off for "unlikely enough" is set from all tested pairs at once (Benjamini-Hochberg, false discovery rate 1%), so it adapts to the size of the dataset.
6. **Link** a pair when it passes the test and shares at least 2 items in one signal, or one text of at least 10 words. One shared repost, link, reply or short text never links anyone. (The long-text rule was added on 14.11 after measuring it: see `docs/evaluation.md`.)
7. **Group** linked accounts. A group of at least 3 accounts is a cluster.
7b. **Rate cap** (`rate_cap` 10, **copied text only** since 15.11): a text item counts toward the chance rate as if at most 10 accounts shared it, because a large botnet's own copies otherwise set the rate (humans share 11-16 times less often than the uncapped rate predicts, Test A). The cap was chosen with labels visible: 3 and 5 made the synthetic look-alikes into clusters, 10 is the smallest tried that does not. **Not for links, reposts or replies** (15.11): many accounts sharing one breaking-news link, reposting one viral post or answering one popular post is what people do. Capped, every pair of commenters who answered both a thread's story and its top comment linked, and on one day of real election retweets a cluster of 19,987 ordinary accounts formed, 266 flagged per 1,000, while the true rate linked none (`docs/evaluation.md`). **Accounts seen in one thread only** (every post has the same `thread_id`: no history fetched, or none exists) drop their `reply` items before pairing, since replying to that thread's posts is what being in it means; their copied text, links and reposts still count, so a review page's copy-paste swarm is still found. The result marks them `thread_only`. (A group-level test was tried the same night and removed: on Fox8, Test A and Cresci it changed recall by at most 0.05 and added false positives, and it held every loosely linked pair in memory.)
8. **Confidence** of a cluster: for each member, the share of its items that another member also has, per kind, averaged with each kind weighted by how many of the cluster's links it carries (kinds the member never posts in are left out); then the average over members. (Over all kinds, Fox8-23's ChatGPT-written botnet scored 0.24: its own text, which nobody copies, diluted the reposts that link it.) A cluster is reported when its confidence is at least 0.2.

The exact SQL is in `backend/swarm/detect.py`.

**Created together.** Two accounts created within 30 days of each other (both need `created_at`) count as one more shared item, but only on top of shared content: creation alone never links anyone. The chance of it is measured from the data like every other item's. A pair created together is tested twice, on its content alone and with the creation added as one more item; the stronger test counts, and the second carries a Bonferroni factor 2 (so for such pairs the false-positive rate can reach 1.5 times the nominal one). Adding the creation to every dated pair came first and weakened strong text pairs on a labelled run, which is why the test runs both ways. In the result it shows as `edges[].created_together` and the `created_together` entry of `signals` (accounts counted, and links it made stronger; those links are also counted under their content kind).

**Member flags.** A cluster's members are not equally part of the swarm: a real community bridged into a botnet by a few links would inherit the botnet's confidence. A member is **flagged** when its own copied share is at least `member_ratio` (default 0.5) times the cluster's unrounded confidence; the others stay in the cluster as linked, not flagged. The result has `accounts[].flagged` and `flagged_members` per cluster, and the metrics count only flagged members. The value 0.5 was not tuned on labels; a fixed cut of 0.5 was tried first and dropped after a labelled run (`docs/evaluation.md`).

### Parameters

| Name | Default | Meaning |
|---|---|---|
| `MIN_WORDS` | 5 | Shorter texts ("good morning") are reused innocently. |
| `MIN_SHARED` | 2 | Fewest shared items in one signal for a link. |
| `LONG_WORDS` | 10 | One shared text of at least this many words is enough for a link, if it passes the chance test. Fixed at twice `MIN_WORDS` before it was measured. |
| `ALPHA` | 0.01 | False discovery rate of the chance test. |
| `MIN_SIZE` | 3 | Smallest cluster. |
| `MIN_CONFIDENCE` | 0.2 | Lowest confidence that is reported. |
| `PAIR_BUDGET` | 1,000,000,000 | Most account-pair rows built in step 4. |

### Scale

Work grows with the number of comments, except step 4, which grows with the square of how many accounts share one item. `PAIR_BUDGET` bounds it: when the data would exceed the budget, the most widely shared items are left out, with a warning that says how many. Those are the items that say least. DuckDB keeps its tables in a temporary file, so the input may be larger than memory.

## Output

One JSON document, the same from the command line and the API. It is self-contained, so a result produced locally can be uploaded to the website later.

```json
{
  "source": {"comments_file": "comments.csv", "profiles_file": "profiles.csv",
             "comments": 5773, "accounts": 256, "synthetic": true},
  "parameters": {"min_words": 5, "min_shared": 2, "long_words": 10, "alpha": 0.01, "min_size": 3, "min_confidence": 0.2},
  "signals": {
    "text":   {"status": "used", "items": 5448, "links": 41},
    "repost": {"status": "skipped", "reason": "column repost_of is missing", "items": 0, "links": 0}
  },
  "warnings": ["comments.csv has no thread_id, likes, client, language columns."],
  "clusters": [
    {
      "id": "477b0a2c01",
      "size": 8,
      "confidence": 0.375,
      "accounts": [{"username": "troll_0_0", "copied_share": 0.375}],
      "edge_count": 28,
      "edges": [{"source": "troll_0_0", "target": "troll_0_1", "kind": "text", "shared": 6}],
      "top_items": [{"kind": "text", "value": "@user_120 rising in rising last the wages",
                     "accounts": 8, "first_seen": "2026-11-01T03:13:55Z", "last_seen": "2026-11-01T03:14:21Z"}],
      "first_seen": "2026-11-01T03:13:55Z",
      "last_seen": "2026-11-01T22:19:31Z",
      "created_within_30_days": {"accounts": 8, "of": 8},
      "declared_automation": null
    }
  ],
  "metrics": null
}
```

- `clusters` are sorted by confidence, highest first, then by size.
- `edges` holds at most the 500 strongest links and `top_items` the 20 most widely shared items, so one huge cluster cannot make the file unusable. `edge_count` is the true number.
- `created_within_30_days` is `null` without creation dates.
- `declared_automation` counts the members that say they are automated ("newsbot", "weather_feed", "Tech RSS" in the username or display name; "bot", "RSS", "automated" in the bio; a denial such as "not a bot" does not count). `null` when none does. It is a description, not a verdict: it changes no confidence and hides no cluster. See "Feeds and swarms" below.
- `metrics` is filled when `profiles.csv` has labels: counts and precision, recall and false-positive rate at the chosen cut, the same at a fixed list of cuts, and the share flagged per label.

## Evaluation

- **Labelled data:** Cresci 2017. Reported per bot family, never as one pooled number, because the families behave differently.
- **Labels measure, they do not train.** Hays et al. (2023) showed that on this dataset one question ("has the account ever tweeted *earthquake*?") separates humans from bots with 0.98 accuracy, because of how the human accounts were collected. A model trained on the labels would learn that, not bot behaviour. The core has no trained parts. The one number picked with the labels visible is `MIN_CONFIDENCE`, and every table that shows results says so.
- **Synthetic cases** cover what Cresci lacks: breaking news, one viral repost, a common greeting, a fan community, and benign automated feeds. Each is a test.

## Known limits

- **Benign automation is flagged.** News feeds that post the same wire text are coordinated by this definition. The synthetic set contains three, and they are reported with confidence 1.0. They are marked with `declared_automation` when their names say so (see "Feeds and swarms"), but the core cannot prove a feed harmless.
- **Languages without spaces.** Words are runs of letters, so a Chinese or Japanese sentence counts as one word and gives no text item (Thai splits at vowel marks, not at words). Such comments are compared only by their links, reposts and replies.
- **Reworded copies are missed** unless the optional similar-text layer is on.
- **Loose groups are missed.** Accounts that share under 20% of their content with each other fall below the default cut. Measured with planted swarms: 6 copied messages are found with up to 24 own posts per member and missed with 30.
- **Small data proves little.** With few comments the chance test rarely passes, by design. The long-text rule helps most here: on Cresci thinned to 10 comments per account, recall went from 0.12 to 0.78.
- **All signals share one chance test.** A signal that adds many weak pairs makes the test stricter for every signal. A trial near-duplicate signal lowered recall on thinned data for this reason and was not adopted.
- **Big swarms hide small evidence.** A large swarm's own copies raise `S`, which makes every other pair look less surprising. Measured in Test A: when most accounts in a time window belong to one botnet, recall falls as each account's history grows (0.94 at 10 comments per account, 0.36 at 20). Estimating `S` again without the accounts already found fixes that but flags most humans on the full data (`docs/evaluation.md`).
- **The profile file adds evidence only,** not confidence. See finding 5.
- **Timing is not used for linking.** A swarm that shares nothing but reacts within seconds is not found.

### Feeds and swarms

A benign feed and a bot swarm can look the same to the core: both post the same text, often within seconds. Posting style does not tell them apart either. In Cresci the bot accounts reply in 5% of their posts and mention someone in 9.5%, against 26% and 61% for humans, so a rule such as "broadcasts, does not address people" would mark the bot swarms as feeds.

What a benign feed usually does and a swarm avoids is **say what it is**. `declared_automation` reports only that: how many members call themselves a bot, a feed or RSS in their name or bio. Rules:

- It changes nothing else: same clusters, same confidence, same order (a test checks this).
- It is a reason to look at the source, never a reason to dismiss a cluster. A swarm can pose as a feed, and one that does is still reported in full.
- It needs only usernames, so it works on scraped comment sections without profiles.
- It cannot be measured on Cresci: our conversion keeps numeric account ids and no bios, so no Cresci cluster is marked (0 of 21). On the synthetic sample the three feeds are marked and both swarms are not.
- Known gaps: a name such as "Talbot" matches; feeds that do not name themselves are not marked.

## Optional layer: similar text

Catches copies that were reworded. A static embedding model (model2vec, runs on a CPU) turns each distinct text into a vector. Texts whose vectors are nearly parallel (cosine at least 0.9) become one item of a fifth signal, `similar_text`, and go through the same steps 3–8.

- Off by default. Needs `model2vec` (in `requirements.txt`) and a one-time model download (`python -m swarm.similar download`).
- **Model:** `minishlab/potion-multilingual-128M` by default (512 MB download, about 1.9 GB of memory, 4 s to load). `--similar-model minishlab/potion-base-8M` is the English-only model used before (30 MB, 150 MB of memory). Measured 14.11:
  - on English data the multilingual model finds the same planted swarms, at equal or higher confidence, with 0 background accounts flagged;
  - among 20,000 distinct background texts it puts 293 pairs above the cut, the English model 3,087, so far fewer unrelated texts are joined;
  - on hand-written Finnish texts, unrelated pairs score at most 0.43 with it and 0.73 with the English model.
- **Rewording with synonyms is still missed.** Three Finnish rewordings that swap words for synonyms score 0.79–0.85 with the multilingual model, under the 0.9 cut. The English model scores them 0.88–0.95 (two over the cut) because it rewards shared letters, the same reason it joins ten times more unrelated texts. A cut of 0.8 would catch them, but it chains the synthetic sample's texts into one group of over 200, which is then left out, so the cut stays at 0.9.
- **Its chance rate counts all texts.** `N` is each account's number of distinct texts (a group of similar texts counts once) and `S` the chance that two of them fall in the same group. Until 14.11 both were computed among grouped texts only, so a swarm whose copies were the only near-duplicates set its own rate (`S` = 0.05 in a small test) and was not found; a test now covers that case.
- Up to 50,000 distinct texts every pair is compared; above that random-projection hashing picks the pairs to compare (about 98.6% of the pairs at the 0.9 cut, nearly all closer ones; a warning says so), up to 1,000,000 distinct texts. Above that, or with too many near-duplicate pairs, the signal is skipped with a reason.
- Cresci's bots copy word for word, so its benefit there is zero by construction.

It is the last task in the build plan and the first to cut.

## Interfaces

- **Command line:** `python -m swarm comments.csv [--profiles profiles.csv] [--out result.json] [--min-confidence 0.2]`. Warnings go to standard error, a short summary to standard output. A bad input ends with a one-line message and exit code 2, never a traceback.
- **Library:** `swarm.core.analyze(comments_path, profiles_path=None, **parameters)` returns the output as a dictionary.
- **HTTP API** (read-only, for the dashboard): serves one result. The paths stay as they are in `docs/api.md`; the fields change to the output above. `verdict` is removed; `confidence` replaces it.

## Left to the builder

- Wording of warnings and of the command-line summary.
- Internal table and helper names beyond those the build plan fixes.
- How the temporary database file is created and removed.

## Not in part 1

Interfaces that part 2 will need from the backend, listed so nobody builds them twice:

- `POST` endpoint that accepts the two CSV files and returns the result (the default "run on Hostinger" mode).
- Upload of a locally produced result file, for the connected tools.
- A language-model explanation per cluster.
- Collecting a site's comments into `comments.csv` from a link.

## Sources

- Pacheco et al. 2021, *Uncovering Coordinated Networks on Social Media*, arXiv 2001.05658
- Luceri et al. 2024, *Unmasking the Web of Deceit*, arXiv 2310.09884
- Mannocci et al., *Detection and Characterization of Coordinated Online Behavior: A Survey*, arXiv 2408.01257
- Hays et al. 2023, *Simplistic Collection and Labeling Practices Limit the Utility of Benchmark Datasets for Twitter Bot Detection*, arXiv 2301.07015
- Cresci et al. 2017, *Social Fingerprinting*, arXiv 1703.04482; and the dataset paper, *The Paradigm-Shift of Social Spambots*, WWW '17
- Yang & Menczer 2023, *Anatomy of an AI-powered malicious social botnet*, arXiv 2307.16336
- Tumminello et al. 2011, *Statistically validated networks in bipartite complex systems*, arXiv 1008.1414
