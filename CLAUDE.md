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
- Edit only that role's directories. If a change is needed elsewhere, say so and let the user ask the owner.
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
- Update only the status block of the current user's role.

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
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/uvicorn swarm.api:app --reload                            # API on :8000 with synthetic data
POSTS_FILE=../data/raw/posts.jsonl .venv/bin/uvicorn swarm.api:app  # API on a real dataset
python -m swarm.synthetic                                           # evaluation on synthetic data
python -m pytest -q                                                 # tests (needs pytest)
docker build -t swarm-backend .                                     # image; serves on port 8000
```

Front end and deploy: not written yet.

## Architecture

**This section and "Commands" describe the first skeleton, which is being replaced.** The core is built from `docs/core-plan.md`; its task 7 rewrites both sections. The skeleton's 60-second rule was measured to be the wrong signal on real data (`docs/core-design.md`, "What the data showed").

- `backend/swarm/detect.py`: the detection. Posts are grouped by shared content (normalised text, link, reposted post). Two accounts are linked when they post the same content within `WINDOW_SECONDS` on at least `MIN_SHARED` separate occasions; one shared post never links anyone, which keeps breaking news and viral posts out. Linked groups of at least `MIN_SIZE` accounts are swarms. `evaluate()` gives account-level precision, recall and false-positive rate from the `coordinated` labels.
- `backend/swarm/synthetic.py`: simulated posts with known swarms and innocent look-alikes, for tests only.
- `backend/swarm/api.py`: read-only FastAPI app. Detection runs once at startup. The contract is `docs/api.md`.
- Not built yet: the decision model (AI Router), the Context.dev live feed, the front end, deploy.
