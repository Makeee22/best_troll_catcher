# Front end

The dashboard for **Spot the swarm**: upload a CSV of posts, get back the groups of accounts ("swarms") that repeatedly post the same content within seconds of each other, with the evidence and the measured precision and false-positive rate.

| Path | What |
|---|---|
| `site/` | The page: static HTML, CSS and plain JavaScript. No build step. (Plan branch B4: **static page**, served by nginx.) |
| `nginx.conf`, `Dockerfile` | nginx serves `site/` and proxies `/api/` and `/health` to the API, so the browser sees one origin. |
| `mock/` | A **mock API**, see below. |
| `mock/samples/` | Example CSV files. Both are **synthetic**. |

The page shows a "SYNTHETIC DATA" badge whenever the API says `source.synthetic: true`.

## The mock API (`mock/`)

**This is a stand-in, not the real backend.** The real API belongs to the backend owner (Arde1001) and its contract is `docs/api.md`.

- It serves the four `GET` endpoints of `docs/api.md` with the same JSON shapes.
- It adds one **proposed** endpoint, `POST /api/analyze` (CSV upload), described at the end of this file.
- The detection is not faked: it imports `backend/swarm/detect.py` read-only, so results match the real backend. `verdict` is always `null`.
- At start it holds the synthetic sample from `backend/swarm/synthetic.py`.
- **One dataset in memory, shared by everybody.** An upload replaces it for all visitors; a restart returns to the synthetic sample. Nothing is written to disk. Fine for a demo, not for several users at once.

## CSV format

UTF-8, first line is the header, one row per post. Separator comma (semicolon is accepted too). Quote text that contains the separator. Limits: 20 MB, 200 000 rows. The columns mirror "Input data format" in `docs/api.md`.

| Column | Required | Meaning |
|---|---|---|
| `id` | yes | Unique per post. |
| `account` | yes | The author's stable id or handle. |
| `timestamp` | yes | ISO 8601, e.g. `2026-11-01T10:00:00Z`. Without an offset it is read as UTC. |
| `text` | yes (cell may be empty) | The post text. Links inside it are found automatically. |
| `links` | no | URLs separated by a space or `\|`. |
| `repost_of` | no | Id of the reposted post. |
| `coordinated` | no | `true` / `false`: the known label. Needed for the metrics. Empty = unknown. |
| `synthetic` | no | `true` for simulated posts. Any `true` row turns the badge on. |

`true`/`false` may also be written `1`/`0` or `yes`/`no`. Extra columns are ignored.

```csv
id,account,timestamp,text,links,repost_of,coordinated,synthetic
2,sock_a,2026-11-01T09:00:05Z,The new harbour plan will ruin this city for everyone,,,true,true
3,sock_b,2026-11-01T09:00:12Z,The new harbour plan will ruin this city for everyone,,,true,true
6,anna,2026-11-01T10:30:00Z,Breaking: bridge closed after storm https://news.example/bridge,https://news.example/bridge,,false,true
```

Samples: `mock/samples/tiny_synthetic_example.csv` (20 hand-written rows, one swarm of 3) and `mock/samples/synthetic_sample.csv` (4413 rows; recreate with `python mock/make_sample.py`).

## Run locally

Without Docker (Python 3.12+), from `frontend/mock/`:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app:app --reload --port 8000   # Windows: .venv\Scripts\uvicorn
```

Open <http://localhost:8000/>. Run this way, the mock also serves the page and the samples, so nothing else is needed.

With Docker, from the repo root:

```bash
docker compose up --build        # page on http://localhost/
```

To point the page at another API: edit `site/config.js`, or add `?api=http://host:8000` to the page URL.

The explanation of "flagged" on the page quotes the thresholds in `backend/swarm/detect.py` (60 seconds, 3 occasions, 3 accounts). If the data owner changes them, update the sentence in `site/index.html`.

## Proposal for the backend: `POST /api/analyze`

For Arde1001. This is what the page calls and what the mock does; change what you like and write the final version into `docs/api.md`.

**Request:** `multipart/form-data` with one part named `file`: a CSV in the format above.

```bash
curl -F "file=@posts.csv" http://localhost:8000/api/analyze
```

**Response `200`:** exactly the body of `GET /api/swarms` for the uploaded data. `source.name` is the uploaded file name; `source.synthetic` is `true` if any row has `synthetic=true`.

**Effect:** the uploaded data becomes the current dataset, so `GET /api/swarms`, `GET /api/swarms/{id}` and `GET /api/metrics` answer for it from then on. `metrics` is `null` when no row has a `coordinated` value.

**Errors:** JSON `{"detail": "message for the user"}`; the page shows `detail` as it is.

| Status | When |
|---|---|
| `400` | Empty file; not UTF-8; a required column is missing; an `id`, `account` or `timestamp` cell is empty; a timestamp is not ISO 8601; an id appears twice; `coordinated` or `synthetic` is not true/false; a row has more values than the header. Row errors name the line. |
| `413` | File over 20 MB, or more than 200 000 rows. |
| `422` | No `file` part (FastAPI's default). |

**Also needed:** CORS has to allow `POST` (now only `GET`), and the `python-multipart` package.

**Open questions for you:**
- One shared dataset is the simplest thing, but two people uploading at once overwrite each other. A dataset id in the response (`/api/swarms?dataset=…`) would fix it if there is time.
- On the public URL anybody can upload. The size limits keep one request cheap; say if you want it locked down more.
- The CSV parsing is in `frontend/mock/app.py` (`parse_csv`), about 60 lines: take it as it is if it helps.
