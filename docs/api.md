# API contract

The only meeting point between the front end and the backend. Owner: backend (Arde1001). The backend changes this file and the code together, and tells the front-end owner.

**What changed on 14.11.** The first skeleton is gone. The input is now two CSV files, and the output is one result document. `verdict` no longer exists: `confidence` (a number from 0 to 1) replaces it. The method behind the numbers is in `docs/core-design.md`; this file only says what you get and how to ask for it.

- All endpoints are `GET`, return JSON, need no login, and allow any origin (CORS).
- Times are ISO 8601 in UTC, like `2026-11-01T03:56:26Z`. A time is `null` when the data has no timestamps.
- Local base URL: `http://localhost:8000`. Interactive docs: `/docs`.
- The API is read-only. It serves **one** result, fixed when the server starts. To show other data, restart it with other settings (below).
- The examples are real output from the built-in synthetic sample, shortened where marked.

## What the server shows

The first of these that is set wins:

| Environment variable | Meaning |
|---|---|
| `RESULT_FILE` | A JSON file written by the command line (`--out`). Served as it is. |
| `COMMENTS_FILE` (and optionally `PROFILES_FILE`) | Analysed once at startup, with the default settings. |
| none | The built-in **synthetic** sample. `source.synthetic` is `true`. |

If a file is set but cannot be read or is not valid, the server **does not start** and prints one line saying which variable is wrong. It never falls back silently to the sample.

The Docker image listens on port 8000. Mount the data file into the container and point the variable at it.

## `GET /health`

```json
{"status": "ok"}
```

## `GET /api/swarms`

The detected clusters of accounts that probably act together, highest `confidence` first, then largest. Each is called a swarm here. Only clusters at or above `parameters.min_confidence` are listed.

Shortened: the example shows two of the three swarms and the `warnings` list is cut to its first entry.

```json
{
  "source": {"comments_file": "comments.csv", "profiles_file": "profiles.csv",
             "comments": 5773, "accounts": 256, "synthetic": true},
  "parameters": {"min_words": 5, "min_shared": 2, "alpha": 0.01, "min_size": 3, "min_confidence": 0.2},
  "signals": {
    "text":   {"status": "used", "reason": null, "items": 5483, "links": 41},
    "link":   {"status": "used", "reason": null, "items": 60, "links": 0},
    "repost": {"status": "used", "reason": null, "items": 240, "links": 0},
    "reply":  {"status": "skipped", "reason": "column parent_id is missing or empty", "items": 0, "links": 0}
  },
  "warnings": [
    "comments file: missing columns thread_id, parent_id, links, likes, client, language; the signals that need them are skipped"
  ],
  "swarms": [
    {
      "id": "a6bb090b21",
      "size": 3,
      "confidence": 1.0,
      "edge_count": 3,
      "first_seen": "2026-11-01T01:23:20Z",
      "last_seen": "2026-11-01T18:03:30Z",
      "sample": {"kind": "text",
                 "value": "WIRE: travel at town than year in wages for schools many wages budget less",
                 "accounts": 3, "first_seen": "2026-11-01T01:23:20Z", "last_seen": "2026-11-01T01:23:22Z"}
    },
    {
      "id": "477b0a2c01",
      "size": 8,
      "confidence": 0.375,
      "edge_count": 28,
      "first_seen": "2026-11-01T03:56:26Z",
      "last_seen": "2026-11-01T19:26:32Z",
      "sample": {"kind": "text",
                 "value": "@user_070 cook home more at new rising plan for a stay roads budget",
                 "accounts": 8, "first_seen": "2026-11-01T03:56:26Z", "last_seen": "2026-11-01T03:56:44Z"}
    }
  ]
}
```

| Field | Meaning | Use in the UI |
|---|---|---|
| `source.synthetic` | `true` when the data is simulated. | **Always show it**, e.g. a "synthetic data" badge. |
| `parameters` | The settings of this run. | Show them next to the numbers. |
| `signals` | One entry per kind of evidence (`text`, `link`, `repost`, `reply`, plus `similar_text` when requested): `used` or `skipped` (with a `reason`), how many shared items it found and how many account pairs it linked. | Show which signals ran. |
| `warnings` | Plain sentences about the input, e.g. columns that were missing. | Show them; they explain weak results. |
| `id` | Stable for the same set of accounts; safe to use in URLs. | |
| `confidence` | 0 to 1: on average, the share of a member's own content that another member also has. Not a probability. See `docs/core-design.md`. | A bar or a number. |
| `edge_count` | Number of linked account pairs (the true number, even when `edges` is cut). | |
| `sample` | The most widely shared item of the cluster (same shape as one `top_items` entry below), or `null`. | A one-line preview. |

`kind` is the signal that found the item: `text`, `link`, `repost`, `reply`, or `similar_text` (only when the core ran with `--similar-text`; the item is then a group of reworded copies, shown as its earliest text).

**Read this before building the list view:** a harmless automated feed that posts the same wire text is "coordinated" by this definition and can score higher than a real swarm (the first entry above is a synthetic news feed, confidence 1.0). The core cannot tell the two apart; this is listed in `docs/core-design.md` under "Known limits". Show `confidence` and the evidence, not a verdict.

## `GET /api/swarms/{id}`

One cluster with its evidence. `404` with `{"detail": "no such swarm"}` if the id is unknown.

Shortened: the lists `accounts`, `edges` and `top_items` have one to two entries here; real ones are longer (at most 500 `edges` and 20 `top_items`).

```json
{
  "id": "a6bb090b21",
  "size": 3,
  "confidence": 1.0,
  "accounts": [
    {"username": "newsfeed_0", "copied_share": 1.0},
    {"username": "newsfeed_1", "copied_share": 1.0}
  ],
  "edge_count": 3,
  "edges": [
    {"source": "newsfeed_0", "target": "newsfeed_1", "kind": "text", "shared": 5},
    {"source": "newsfeed_0", "target": "newsfeed_2", "kind": "text", "shared": 5}
  ],
  "top_items": [
    {"kind": "text", "value": "WIRE: travel at town than year in wages for schools many wages budget less",
     "accounts": 3, "first_seen": "2026-11-01T01:23:20Z", "last_seen": "2026-11-01T01:23:22Z"}
  ],
  "first_seen": "2026-11-01T01:23:20Z",
  "last_seen": "2026-11-01T18:03:30Z",
  "created_within_30_days": {"accounts": 3, "of": 3},
  "copy_gap_seconds": {"median": 5.0, "items": 5}
}
```

| Field | Meaning | Use in the UI |
|---|---|---|
| `accounts` | The members. `copied_share` is the share of that account's own content that it shares with the cluster. Most copied first. | The member list. |
| `edges` | Linked account pairs. `shared` = how many separate items the two have in common; `kind` = which signal linked them. At most the 500 strongest. | The account graph. |
| `top_items` | The items most accounts of the cluster share, with how many (`accounts`) and when. At most 20. | The evidence list and timeline. |
| `created_within_30_days` | How many of the cluster's accounts were created within one 30-day window (`accounts`), out of those with a creation date (`of`). `null` without creation dates. | A badge, as supporting evidence only. |
| `copy_gap_seconds` | For each shared item that at least two members have a time for: the average time in seconds from one member's copy to the next. `median` is the median of those gaps, over `items` shared items. `null` when no shared item has two times. Evidence only: it never changes which clusters are listed or their `confidence`. | A line such as "copies follow each other within seconds". |

## `GET /api/metrics`

How well detection does on labelled data. `metrics` is `null` when the profile file has no `label` column.

Shortened: `by_threshold` lists six cuts in the real output; the example shows two.

```json
{
  "source": {"comments_file": "comments.csv", "profiles_file": "profiles.csv",
             "comments": 5773, "accounts": 256, "synthetic": true},
  "metrics": {
    "labelled_accounts": 256,
    "labelled_without_content": 0,
    "at_min_confidence": {
      "min_confidence": 0.2,
      "true_positives": 13, "false_positives": 3, "false_negatives": 0, "true_negatives": 240,
      "precision": 0.8125, "recall": 1.0, "false_positive_rate": 0.0123
    },
    "by_threshold": [
      {"min_confidence": 0.2, "true_positives": 13, "false_positives": 3, "false_negatives": 0,
       "true_negatives": 240, "precision": 0.8125, "recall": 1.0, "false_positive_rate": 0.0123},
      {"min_confidence": 0.5, "true_positives": 0, "false_positives": 3, "false_negatives": 13,
       "true_negatives": 240, "precision": 0.0, "recall": 0.0, "false_positive_rate": 0.0123}
    ],
    "by_label": {
      "human": {"accounts": 240, "flagged": 0},
      "benign_feed": {"accounts": 3, "flagged": 3},
      "bot:swarm_0": {"accounts": 8, "flagged": 8}
    }
  }
}
```

Counted per account: a flagged account is one that is in a listed cluster. `by_label` shows how many accounts of each label were flagged. The labels are only used to measure, never to train. The cut `min_confidence` is the one value chosen with the labels visible; **say so wherever these numbers are shown**.

## Command line

For people who run the core themselves. Python 3.12+ and `pip install -r requirements.txt` in `backend/`.

```bash
python -m swarm COMMENTS [--profiles FILE] [--out FILE] [--min-confidence X] [--similar-text] [--ignore FILE]
```

- Warnings go to standard error, one per line, starting with `warning: `.
- Standard output is a short summary: one line per signal, the number of clusters, one line per cluster (id, size, confidence), and, with labels, precision, recall and false-positive rate at the cut. If the data is synthetic, the first line says so.
- `--out FILE` writes the full result as JSON. That file is what `RESULT_FILE` expects, and its `clusters` list is what the API calls `swarms`.
- `--similar-text` (optional, off by default) also links accounts that post reworded copies of the same text. It needs `pip install model2vec` and downloads a small model once. It is slower (about 40 s for 80,000 distinct texts) and limited to 100,000 distinct texts. It adds a `similar_text` entry to `signals`. It is skipped, with a reason, when there are fewer than 2 distinct texts, more than 100,000, or too many near-duplicate pairs; groups of more than 200 similar texts are left out as generic.
- `--ignore FILE` leaves accounts out before anything is compared: a text file with one username per line (exact match, blank lines and lines starting with `#` are skipped). Use it for feeds or staff accounts you know are legitimate. The result lists `parameters.ignored_accounts`, and a warning says how many accounts and comments were left out and how many names matched no account. An unreadable file, or a list that removes every comment, is an error. In Python: `analyze(..., ignore_path=FILE)`.
- Links are compared after normalising: the scheme (`http` or `https`), `www.`, tracking parameters (`utm_*`, `fbclid`, `gclid`), the fragment and a trailing slash do not make two links different.
- A bad input ends with one line `error: <what to fix>` and exit code 2, never a traceback.
- `python -m swarm.synthetic DIR` writes the synthetic sample (`comments.csv`, `profiles.csv`) into `DIR`.
- `python -m swarm.cresci SOURCE_DIR OUT_DIR` converts the Cresci 2017 dataset (research use only, never committed) to the same two files.

The same result is available in Python: `swarm.core.analyze(comments_path, profiles_path=None)` returns it as a dictionary.

## Input files

For the data owner. Two CSV files with a header row; the full rules are in `docs/core-design.md`, "Input format". Column names are matched without regard to case or spaces. A semicolon-separated file with a byte-order mark (what Excel makes in Finland) works too. Empty cells mean "unknown". Unknown columns are ignored with a warning.

### `comments.csv`

| Column | Used for | If missing |
|---|---|---|
| `username` | The account. **Required.** | The run stops with an error. |
| `text` | Signals `text` and `link` | Those signals are skipped. |
| `links` | Signal `link`. URLs separated by spaces. URLs inside `text` are found automatically. | Only URLs inside `text` are used. |
| `repost_of` | Signal `repost`: the id of the reposted comment | Signal skipped. |
| `parent_id` | Signal `reply`: the id of the comment this one answers | Signal skipped. |
| `timestamp` | First and last time seen. ISO 8601; without an offset it is read as UTC. | Times are empty in the output. |
| `comment_id` | Pointing to example comments | Row numbers are used. |
| `synthetic` | `1` or `true` marks simulated data | Treated as real data. |
| `thread_id`, `likes`, `client`, `language` | Accepted, not used yet | Nothing. |

### `profiles.csv` (optional)

| Column | Used for | If missing |
|---|---|---|
| `username` | Joining to comments. **Required in this file.** | The file is ignored with a warning. |
| `created_at` | The `created_within_30_days` evidence | The line is left out. |
| `label` | Measuring. `human`, `bot`, or `bot:<family>`. Anything not starting with `bot` counts as not a bot. | No metrics. |
| `display_name`, `bio`, `followers`, `following`, `post_count`, `default_avatar`, `verified`, `location`, `ip_hash`, `user_agent_hash`, `email_domain` | Accepted, not used yet | Nothing. |

`ip_hash`, `user_agent_hash` and `email_domain` must be hashed before they reach the file. The core never writes them to its output.

### What is truly required

- `username`, and
- at least one of `text`, `links`, `repost_of`, `parent_id`.

Everything else, including `timestamp` and the whole profile file, only adds evidence. The more columns, the more signals run; the `signals` and `warnings` fields of the result say what was used.
