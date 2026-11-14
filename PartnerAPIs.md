# Partner APIs

Which Junction partner offers are worth an account for this project (Spot the swarm, for the Hostinger and Context.dev challenges). Judged from the partners' descriptions only: none of these APIs has been tested yet.

What the project needs:
1. **A language model** for the decision model. Covered by Hostinger AI Router.
2. **Live web data.** Covered by Context.dev, which is also our second challenge.
3. **Posts with accounts and timestamps.** The open gap (`PLAN.md`, B8 and B11).
4. **Text similarity** (embeddings), if hashing is not enough (B10).
5. **Hosting.** Must be Hostinger: the final product has to run there.

Status: `USE` = in the product, `ON DEMAND` = sign up only when the stated trigger happens, `SKIP` = no use for us.

## Priority list

| # | Partner | Offer | Status | Best use for us | Sign up when |
|---|---|---|---|---|---|
| 1 | **Hostinger** | VPS, AI Router credits, AI Builder | USE | Hosting and the decision model | done |
| 2 | **Context.dev** | 50,000 credits per team; search, scrape, schema extraction, news, monitors + webhooks | USE | The live feed into ingest; required for the second challenge | now |
| 3 | **Oxylabs** | `/search` and `/scrape`, handles proxies, JavaScript and bot challenges | ON DEMAND | Collecting posts from comment sections, forums or social pages that block ordinary scrapers. The strongest candidate for closing gap 3. | B11 picks a source that Context.dev cannot scrape |
| 4 | **OpenAI** | $100 per participant | ON DEMAND | Embeddings for text similarity; a second model to cross-check verdicts; Codex for coding | AI Router has no embedding model, or its credits run low |
| 5 | **Claude API** | $20 per participant | ON DEMAND | Extra budget for coding tools or for the decision model | credits run low |
| 6 | **Exa** | $50 per participant; meaning-based search, date and domain filters, past versions of pages | ON DEMAND | Tracing one narrative or copied article across many sites, with dates | B11 goes toward copied content across domains |
| 7 | **Gemini** | API credits for eligible participants | ON DEMAND | Backup model; large inputs (a whole swarm's posts in one call) | a swarm's evidence does not fit the chosen model |
| 8 | **Modal** | $100 per participant; Python functions on cloud CPUs and GPUs | ON DEMAND | A one-off heavy batch job, e.g. embedding a multi-million-post dataset | a dataset is too big for the VPS (2 cores, 8 GB) |
| 9 | **IronShard** | S3-compatible buckets | ON DEMAND | Sharing a dataset over 100 MB with judges | judges need our raw data; inside the team the VPS disk does the same job |
| 10 | **Featherless** (API) | $50 in credits for open-weight models | SKIP | Overlaps AI Router | — |
| 11 | **Verda** | €200 of GPU cloud | SKIP | We train no models | — |
| 12 | **Featherless** (bare-metal GPU) | GPU servers on request | SKIP | Same | — |
| 13 | **Aiven** | $50 for managed databases | SKIP | SQLite on the VPS is enough, and an outside database weakens "runs on Hostinger" | — |
| 14 | **CRACI** | CI/CD runners with dependency tracking | SKIP | Deploy is one SSH command; no time for a pipeline | — |
| 15 | **Cloudinary** | Image and video hosting | SKIP | The product has no media | — |

## Notes

- **Only Context.dev needs an account right now.** Everything else can wait for its trigger, and most triggers depend on B11.
- **Oxylabs and Exa overlap with Context.dev.** Using Context.dev for everything it can do is better for the second challenge. Bring in another scraper only for what Context.dev cannot reach.
- **Keep heavy outside dependencies out of the live path.** Hostinger allows hosted models, but the product itself must run on their server. Modal, IronShard and the like are for one-off preparation work, not for serving the demo.
- **Check first:** does AI Router offer an embedding model? If yes, item 4 drops to "credits run low" only.
