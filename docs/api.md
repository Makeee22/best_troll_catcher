# API contract

> **Changing on 14.11.** This file describes the first skeleton, which is still what `main` runs. The core that replaces it has a new input format (two CSV files) and a new output (`confidence` instead of `verdict`). Both are specified in `docs/core-design.md`, sections "Input format" and "Output". Build new front-end work against those. This file is rewritten when the core lands.

The only meeting point between the front end and the backend. Owner: backend (Arde1001). The backend changes this file and the code together, and tells the front-end owner.

- All endpoints are `GET`, return JSON, need no login, and allow any origin (CORS).
- Timestamps are ISO 8601 with a UTC offset.
- Local base URL: `http://localhost:8000`. Interactive docs: `/docs`.
- `verdict` is `null` until the decision model exists. Build the UI for both cases.

## `GET /health`

```json
{"status": "ok"}
```

## `GET /api/swarms`

The detected swarms, largest first.

```json
{
  "source": {"name": "synthetic sample", "synthetic": true, "posts": 4413, "accounts": 216},
  "swarms": [
    {
      "id": "477b0a2c01",
      "size": 8,
      "edge_count": 28,
      "post_count": 48,
      "first_seen": "2026-11-01T03:13:55.047253+00:00",
      "last_seen": "2026-11-01T22:19:31.530097+00:00",
      "sample_text": "@user_120 rising in rising last the wages",
      "verdict": null
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `source.synthetic` | `true` when any of the data is simulated. **The UI must show this**, e.g. a "synthetic data" badge. |
| `id` | Stable for the same set of accounts; safe to use in URLs. |
| `size` | Number of accounts in the swarm. |
| `edge_count` | Number of account pairs that are linked. |
| `post_count` | Number of posts that serve as evidence. |

## `GET /api/swarms/{id}`

One swarm with its evidence. `404` if the id is unknown.

```json
{
  "id": "18b23f64b4",
  "size": 5,
  "accounts": ["troll_1_0", "troll_1_1", "troll_1_2", "troll_1_3", "troll_1_4"],
  "edges": [
    {"source": "troll_1_0", "target": "troll_1_1", "shared": 6}
  ],
  "first_seen": "2026-11-01T02:43:46.782588+00:00",
  "last_seen": "2026-11-01T19:01:25.084424+00:00",
  "posts": [
    {
      "id": "syn4343",
      "account": "troll_1_0",
      "timestamp": "2026-11-01T02:43:46.782588+00:00",
      "text": "@user_129 to and many for council many wages than many"
    }
  ],
  "verdict": null
}
```

| Field | Meaning | Use in the UI |
|---|---|---|
| `edges` | Linked account pairs. `shared` = on how many separate occasions the two posted the same content within the time window. | The account graph. |
| `posts` | The evidence posts, oldest first. | The timeline. |

### `verdict` (planned, not built yet)

```json
{
  "label": "coordinated",
  "confidence": 0.9,
  "reasons": ["Eight accounts posted six identical messages within 30 seconds of each other."],
  "innocent_explanations": ["Breaking news: ruled out, the messages link to no news event."]
}
```

`label` is one of `coordinated`, `probably_organic`, `unclear`.

## `GET /api/metrics`

How well detection does on labelled data. `metrics` is `null` when the data has no labels.

```json
{
  "source": {"name": "synthetic sample", "synthetic": true, "posts": 4413, "accounts": 216},
  "metrics": {
    "labelled_accounts": 216,
    "true_positives": 13,
    "false_positives": 3,
    "false_negatives": 0,
    "true_negatives": 200,
    "precision": 0.8125,
    "recall": 1.0,
    "false_positive_rate": 0.0148
  }
}
```

Counted per account: a flagged account is one that appears in any swarm.

## Input data format

For the data owner. The backend reads one file of posts in JSON Lines: one JSON object per line.

```json
{"id": "123", "account": "some_user", "timestamp": "2026-11-01T10:00:00Z", "text": "Post text https://example.org/a", "repost_of": null, "coordinated": false}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique per post. |
| `account` | yes | The author's stable id or handle. |
| `timestamp` | yes | ISO 8601. Without an offset it is read as UTC. |
| `text` | no | The post text. Links inside it are found automatically. |
| `links` | no | List of URLs, if the dataset gives them separately. |
| `repost_of` | no | Id of the reposted post. |
| `coordinated` | no | The label, when known: `true` if the account is part of a known coordinated campaign. Needed for the metrics. |
| `synthetic` | no | `true` for simulated posts. |

Put the file in `data/raw/` (not committed) and start the backend with `POSTS_FILE=path/to/file.jsonl`.
