# Front end

The dashboard for **Spot the swarm**: upload a comments CSV (and optionally a profiles CSV), get back the groups of accounts that share content more often than chance predicts, each with a confidence, the evidence, and, when the profiles carry labels, the measured precision and false-positive rate.

| Path | What |
|---|---|
| `site/` | The page: static HTML, CSS and plain JavaScript. No build step. (Plan branch B4: **static page**, served by nginx.) |
| `nginx.conf`, `Dockerfile` | nginx serves `site/` and `samples/`, and proxies `/api/` and `/health` to the API, so the browser sees one origin. |
| `api/` | The backend's API plus an upload endpoint, see below. |
| `samples/` | The synthetic sample from `python -m swarm.synthetic` (`synthetic_comments.csv`, `synthetic_profiles.csv`). Every row is marked synthetic. |

The page builds against `docs/api.md`. It shows a "SYNTHETIC DATA" badge whenever `source.synthetic` is true, the input warnings and which signals ran, each swarm's confidence and evidence, and the metrics at every confidence cut, with the note that the cut was chosen with the labels visible.

## The API (`api/`)

`api/app.py` is **not a mock**. It imports `backend/swarm/api.py` unchanged, so every `GET` endpoint is the backend's own, and adds one endpoint the backend does not have yet (it is part 2 in `docs/core-design.md`):

**`POST /api/analyze`**: `multipart/form-data` with a part `comments` (CSV, required) and optionally `profiles` (CSV), in the format of `docs/api.md`, "Input files".

```bash
curl -F comments=@comments.csv -F profiles=@profiles.csv http://localhost:8000/api/analyze
```

- `200`: the same body as `GET /api/swarms` for the uploaded data. It runs `swarm.core.analyze()`, so the result is exactly what the backend's command line gives. The upload becomes the current result: `/api/swarms/{id}` and `/api/metrics` answer for it.
- `400 {"detail": ...}`: the core's own `InputError` message (no `username` column, nothing to compare, …), with the server's temp path replaced by the file name.
- `413`: the files are over 20 MB together. `422`: no `comments` part.

**One result in memory, shared by everybody.** An upload replaces it for all visitors; a restart returns to what `swarm.api` loads at startup (the synthetic sample). Analyses run one at a time. Nothing is kept on disk.

`api/requirements.txt` adds `python-multipart` and, as a stopgap, `numpy`: `backend/swarm/similar.py` imports numpy at module level but `backend/requirements.txt` does not list it (commit `bfaac31`), so the backend image cannot start without it. Remove the line when the backend fixes it.

When the backend gets its own upload endpoint, switch with `deploy/docker-compose.backend.yml` and delete `api/`.

## Run locally

Without Docker (Python 3.12+), from `frontend/api/`:

```bash
python -m venv .venv
.venv/bin/pip install -r ../../backend/requirements.txt -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app:app --reload --port 8000                                # Windows: .venv\Scripts\uvicorn
```

Open <http://localhost:8000/>. Run this way, the API also serves the page and the samples.

With Docker, from the repo root: `docker compose up --build` (page on <http://localhost/>).

To point the page at another API: edit `site/config.js`, or add `?api=http://host:8000` to the page URL (that API must allow the page's origin; the backend allows any origin for `GET`).

## Data rules

- The samples here are synthetic. Never add real data to this folder: the repo is public.
- **Never upload the Cresci 2017 data to the live site.** It is research-only and holds real people's tweets; the result would be shown to every visitor.
