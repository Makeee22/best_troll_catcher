# CLAUDE.md

Guidance for Claude Code (and any AI coding tool) in this repository. Every teammate's session loads this file, so keep it short. The living plan is in `PLAN.md`.

## Project

A Junction 2026 hackathon project (13–15.11.2026, team of 4) for two partner challenges:

- **Hostinger, "Decode the Noise"** (main): an AI tool that detects propaganda, bots and bad actors online. Our direction is **Spot the swarm**: detect coordinated inauthentic behaviour (bot networks, astroturfing, brigading) from posting timing, account similarity, text reuse and amplification patterns, not from any single post.
- **Context.dev** (second): "a product that reacts to the live web". Their API must be a real part of the product: it feeds live web content into our ingest.

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
| **Backend** | `backend/`, `docs/api.md` |
| **Front end + infrastructure** | `frontend/`, `deploy/`, `docker-compose.yml` |
| **Presentation + documentation** | `docs/pitch/`, `README.md`, `PLAN.md` |
| **Data + detection criteria** | `data/`, `docs/criteria.md` |

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
- `Junction Platform.txt` and `kaikki.pdf` (the event guide and challenge texts) are ignored on purpose: they hold personal data and other partners' keys. Never commit or quote them. Partner promo codes stay out of the repo too.
- Raw datasets go in `data/raw/` (ignored). `data/README.md` records where each one comes from and its license. No file over about 50 MB in git.

## Detection rules

- The language model is the **judge of evidence**, never the only detector. Deterministic signals find the candidates first.
- Every verdict lists its evidence and the innocent explanations that were considered (breaking news, real campaigns, benign automated feeds, one viral post).
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

Not written yet. Fill in once the stack is decided (`PLAN.md`, branch B3): how to run the backend, the front end, the evaluation and a deploy.

## Architecture

Not written yet. The proposed pipeline is in `PLAN.md` under "Approach". Replace this stub with the real structure once the code exists.
