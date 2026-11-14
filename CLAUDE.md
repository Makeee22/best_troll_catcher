# CLAUDE.md

Guidance for Claude Code (and any AI coding tool) in this repository. Every teammate's session loads this file, so keep it short. The living plan is in `PLAN.md`.

## Project

A Junction 2026 hackathon project (13–15.11.2026, team of 4) for two partner challenges:

- **Hostinger, "Decode the Noise"** (main): an AI tool that detects propaganda, bots and bad actors online. Our direction is **Spot the swarm**: find groups of accounts that behave like one actor (bot networks, astroturfing, brigading) from what they share and how, not from any single post. Lone bots are out of scope.
- **Context.dev** (second): "a product that reacts to the live web". Their API must be a real part of the product: it collects the comments of a site the user points at.

The product has two parts (team decision 14.11):

1. **The core** (`backend/`, the MVP): an open-source program anyone can download and run. Input: a CSV of comments and an optional CSV of profiles, in one standard format for any website. Output: a list of account clusters that are probably coordinated, each with a confidence and its evidence. It is purely algorithmic: no language model, no accounts, no paid services. It must scale from a laptop to a large dataset. Design: `docs/core-design.md`; build plan: `docs/core-plan.md`.
2. **The website** (after the MVP): runs the core on Hostinger by default. Connected accounts or API keys (Hostinger AI Router, Gemini, OpenAI, Anthropic, Context.dev) add optional features, such as collecting a site's comments from a link or explaining a cluster in plain language. "Run locally" links to the install instructions on GitHub; a result produced locally can be uploaded to the website for the connected tools.

Not confirmed yet: whether this split fits Hostinger's idea of the challenge. The team asks their mentors when they are back at the venue.

Hard requirements:
- The product **runs live on Hostinger infrastructure with a public URL** the judges can open.
- Judges weigh **the strength and honesty of the detection logic, including false positives**, over a polished front end. We must show measured precision and false-positive rate.
- All code is written during the event. The repo is public under the MIT license.

## Deadlines

| When | What |
|---|---|
| Sat 14.11 23:00 | Feature freeze: bug fixes only after this |
| Sun 15.11 08:30 | Submission set to FINAL on the Junction Platform |
| Sun 15.11 09:30 | No more deploys |
| Sun 15.11 10:00 | Hard deadline; late submissions are not accepted |

The submission needs: name, punchline, description, technologies, a video of **at most 2:00**, demo link, source link, pitch deck as PDF.

## Who owns what

One owner per directory. This is how four people avoid git conflicts.

| Role | Owns |
|---|---|
| **Backend** (Arde1001) | `backend/`, `docs/api.md`, `CLAUDE.md` |
| **Front end + infrastructure** (Makeee22) | `frontend/`, `deploy/`, `docker-compose.yml` |
| **Presentation + documentation** (J0l3s) | `docs/pitch/`, `README.md`, `PLAN.md` |
| **Data + detection criteria** (TheSnowman99) | `data/`, `docs/criteria.md` |

- If it is unclear which role the current user has, ask before editing.
- Code directories belong to their role: edit only that role's directories. If a change is needed elsewhere, say so and let the user ask the owner.
- Documentation (`docs/`, `README.md`, `PLAN.md`, this file) may be edited by anyone. If two edits conflict, tell the user and the original owner's version wins.
- The front end and the backend meet only at `docs/api.md`. The backend owner changes it and announces the change; the front end builds against mock JSON until the real endpoint exists.

## Git rules

- `git pull --rebase` before starting work and before every push (`git config pull.rebase true` once per clone).
- Stage files by name. Never `git add -A` or `git add .`.
- Never force-push and never rewrite `main`.
- Commit and push only when the user asks.
- `main` must stay deployable, because the server builds from it. Half-done or risky work goes on a short branch named `name/topic` and is merged the same day.
- Small commits, often.

## Secrets and data

- API keys live only in `.env`, which is ignored. Never print a key into code, docs, commit messages or logs.
- `Junction Platform.txt`, `kaikki.pdf` and `techpartners.txt` (the event guide, challenge texts and partner notes) are ignored on purpose: they hold personal data and other partners' keys. Never commit or quote them. Partner promo codes stay out of the repo too.
- Raw datasets go in `data/raw/` or `backend/data/` (both ignored). `data/README.md` records where each one comes from and its license. No file over about 50 MB in git.
- The Cresci 2017 dataset in `backend/data/` is for research use only and holds real people's tweets. Never commit it, quote its content, or serve it from the live site. Only aggregate numbers leave the machine.

## Detection rules

- The core is deterministic. No language model decides who is flagged. On the website a language model may explain a cluster the core found, never find or overrule one.
- Every cluster lists its evidence. The innocent look-alikes (breaking news, real campaigns, benign automated feeds, one viral post) each have a test.
- Any input column may be missing. The core warns and skips the signals that need it. It stops only when `username` is missing or no signal can run.
- Labels are used to measure, never to train a model. Bot-detection benchmarks contain shortcuts (see `docs/core-design.md`). The one value picked with the labels visible is the confidence cut; say so wherever results are shown.
- Every change to detection is re-run on the evaluation set, and the new numbers go into `PLAN.md`.
- Synthetic or simulated test data is always labelled as synthetic, in the data and in anything shown to judges.
- Prefer the smallest version that works. No features outside the plan.

## Plan upkeep

- `PLAN.md` holds the timeline, the open decisions ("branches", `B1`…) and a status block per role.
- When a decision is made, mark its branch `DECIDED` with the date and the choice. Keep the other options listed.
- Update the status block of the current user's role; other parts of `PLAN.md` may be edited by anyone (see "Who owns what"), and new evaluation numbers go into its Results table.

## Resources

- **Hostinger VPS** (KVM 2): 2 vCPU, 8 GB RAM, 100 GB disk, root access, Docker, free domain.
- **Hostinger AI Router**: one key for 150+ models, compatible with the OpenAI and Anthropic SDKs. Used for the decision model.
- **Hostinger AI Builder**: optional, for a front end or landing page.
- **Hostinger MCP**: `claude mcp add --transport http hostinger https://mcp.hostinger.com` (browser sign-in). Docs: `docs.hostinger.com/hostinger-connector`.
- **Context.dev**: search, scrape, crawl, news search, monitors with webhooks, batch API. Docs: `docs.context.dev`.
- **Exa** (optional): meaning-based web search and find-similar pages.

## Commands

Backend (Python 3.12+), run from `backend/`:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # once (run-time: requirements.txt)
python -m swarm.synthetic DIR                                           # write the synthetic sample (comments.csv, profiles.csv)
python -m swarm COMMENTS [--profiles FILE] [--out FILE] [--min-confidence X] [--similar-text] [--ignore FILE]   # the core: summary on stdout, JSON with --out; --similar-text needs pip install model2vec
python -m swarm.cresci SOURCE_DIR OUT_DIR                               # convert Cresci 2017 to the standard format
python -m swarm.inject COMMENTS [--out FILE] [--similar-text]           # benchmark: plant simulated swarms into a background file, tabulate what is found
.venv/bin/uvicorn swarm.api:app --reload                                # API on :8000, synthetic sample
RESULT_FILE=result.json .venv/bin/uvicorn swarm.api:app                 # API serving a result written with --out
COMMENTS_FILE=c.csv [PROFILES_FILE=p.csv] .venv/bin/uvicorn swarm.api:app   # API analysing files at startup
.venv/bin/python -m pytest -q                                           # tests
docker build -t swarm-backend .                                         # image; serves on port 8000
```

Front end and deploy: not written yet.

## Architecture

One DuckDB connection per run carries the data through four stages; each is a module that reads and writes named tables. The method is in `docs/core-design.md`, the build plan in `docs/core-plan.md`.

- `backend/swarm/load.py`: reads the two CSV files into the tables `comments` and `profiles`, collects warnings; `InputError` for input that cannot be analysed.
- `backend/swarm/detect.py`: items (shared content per signal), account pairs, the chance test, links, clusters, each member's copied share and the confidence.
- `backend/swarm/evaluate.py`: precision, recall and false-positive rate from the `label` column. Labels measure, they never train.
- `backend/swarm/core.py`: `analyze()` runs the stages and builds the result document.
- `backend/swarm/__main__.py`: the command line, a thin wrapper around `analyze()`.
- `backend/swarm/synthetic.py`: simulated data in the standard format with known swarms and innocent look-alikes (`synthetic = 1` on every comment).
- `backend/swarm/similar.py`: optional `similar_text` signal (reworded copies, via a small static embedding model); off by default.
- `backend/swarm/cresci.py`: converts the Cresci 2017 zips to the standard format.
- `backend/swarm/inject.py`: the injection benchmark. Plants simulated swarms (size, copied messages, own posts, edited or reworded copies) into a background file and runs `analyze()` on each. Run it after every change to detection.
- `backend/swarm/api.py`: read-only FastAPI app serving one result, fixed at startup (`RESULT_FILE`, else `COMMENTS_FILE` + `PROFILES_FILE`, else the synthetic sample). A bad file stops startup with a message. The contract is `docs/api.md`.
- Tests: one `backend/test_*.py` per module; `conftest.py` has the `make_csv` helper.
- Not built yet (part 2, the website): the upload and `POST` endpoints, the language-model explanation, collecting comments with Context.dev, the front end, deploy.
