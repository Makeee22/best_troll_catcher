# Front end

The dashboard for **Spot the swarm**: paste a Bluesky post link, upload a saved Reddit thread page, or upload a comments CSV (and optionally a profiles CSV), get back the groups of accounts that share content more often than chance predicts, each with a confidence, the evidence, and, when the profiles carry labels, the measured precision and false-positive rate.

| Path | What |
|---|---|
| `site/` | The page: static HTML, CSS and plain JavaScript. No build step. (Plan branch B4: **static page**, served by nginx.) |
| `nginx.conf`, `Dockerfile` | nginx serves `site/` and `samples/`, and proxies `/api/` and `/health` to the API, so the browser sees one origin. |
| `api/` | The backend's API plus an upload endpoint and the discussion jobs (Bluesky link, saved Reddit page), see below. |
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

`api/requirements.txt` adds `python-multipart` for the upload.

### Discussion jobs (`api/jobs.py`)

Collecting a discussion takes from seconds to minutes, so it runs as a background job with a random id. The result is **private to that id** (the page puts it in the address as `#job=…`), is kept in memory only, and is deleted after 3 hours. It never replaces the shared result. Caps: 20 jobs per hour, 2 running at a time, 150 participants' histories per job.

**`POST /api/jobs/url`**: JSON `{"url": "https://bsky.app/profile/NAME/post/ID"}`.

```bash
curl -H 'Content-Type: application/json' -d '{"url":"https://bsky.app/profile/bsky.app/post/3mycyypdrxc2s"}' http://localhost:8000/api/jobs/url
```

- `202`: the job (`id`, `status`, `stage`, `progress`, `thread`). A Bluesky post link starts `api/bluesky.py`: the whole thread from Bluesky's public API, then each participant's newest 30 posts, replies and reposts and their profiles, every request through Context.dev (direct to the same public endpoint when Context.dev does not answer in time; `thread.via` counts both).
- `400`: a Reddit link ("save the page and use the Reddit card": Reddit shows its comments only to a browser), a Bluesky link that is not a post, or any other site ("not supported yet").
- `429`: a cap was reached. `503`: `CONTEXT_DEV_API_KEY` is missing on the server.

**`POST /api/jobs/reddit`**: `multipart/form-data` with a part `page`, a Reddit thread page saved from the browser (`api/reddit_html.py` reads the comments; `api/contextdev.py` fetches each commenter's newest 25 comments).

**`GET /api/jobs/{id}`**: `status` is `collecting`, `analysing`, `done` or `failed` (`error` says why). Always: `thread` (`platform`, `title`, `comments_found`, `comments_expected`, `commenters`, `commenters_fetched`, `history_per_commenter`; for Bluesky also `author`, `comments_hidden`, `reposts`, `via`), `histories_ok`, `histories_failed`, `credits_used`, `seconds`. When done: `listing` (the same shape as `GET /api/swarms`) and `metrics`. **`GET /api/jobs/{id}/swarms/{swarm}`** is one cluster, as `GET /api/swarms/{id}`.

The page has a card for each: "Analyse a discussion from a link" (URL field) and "Analyse a Reddit thread" (file). Both show the same progress line, and the result opens with a banner that says what was read (for Bluesky: replies read against Bluesky's own count, participants, reposts, how the data was fetched, seconds and credits) and that a swarm is a lead, not proof.

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

## AI explanation of a swarm (`api/explain.py`)

`POST /api/swarms/{id}/explain` (shared result) and `POST /api/jobs/{job}/swarms/{id}/explain` (a discussion job) ask a
language model (Gemini, `GEMINI_MODEL`, default `gemini-flash-latest`; key `GEMINI_API_KEY` in the server's `.env`) to
explain **the evidence the core already produced** for one cluster: what the group appears to do, observations with
evidence ids (E1… shared items, F1… facts such as copied share, copy gap, creation dates, declared automation), the
innocent explanations weighed (low / medium / high), what to check next and what the evidence cannot show.

- Team rule (CLAUDE.md): the model explains, it never finds or overrules a cluster. The page labels the answer as AI-written.
- Privacy: usernames become "Member 1…n" and @handles / u/names in texts become "@someone" before anything is sent; only
  the cluster's evidence is sent. The page shows exactly what was sent.
- Cached per result and cluster; at most 60 explanations per hour for the whole site. 503 when no key is configured, 429 over the cap.

**News check (`api/newscheck.py`).** Before the model is asked, the three most shared items of the cluster are searched in
Context.dev's news search (`POST /v1/news/search`, natural language, the group's active window ±2 days, 5 articles each,
about 1 credit per item). The hits go to the model as evidence N1…, which it must judge (same story or not) for the
breaking-news look-alike, and to the page. Skipped for synthetic data. @handles are removed from the queries.

**Provider.** Hostinger AI Router first (`HOSTINGER_ROUTER_API_KEY`, model `ROUTER_MODEL`, default `gemini-3.5-flash-eu`,
run in the EU; the router sits behind Cloudflare, which refuses Python's default User-Agent, so a named one is sent), and
Google's Gemini API (`GEMINI_API_KEY`) as fallback; the answer says which one wrote it.
