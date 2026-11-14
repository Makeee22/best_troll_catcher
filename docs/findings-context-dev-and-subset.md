# Findings: what Context.dev can collect, and a false-positive trap

Written 14.11.2026 afternoon by the front-end + infrastructure role (Makeee22), for the backend owner and the team. Relevant to B11 (what Context.dev feeds us) as decided at 13:26: "scrape each commenter's last ~15 comments". The core was `main` at `73def06`/`387e5c6`, run unchanged.

**In short**
1. Context.dev **cannot collect a thread's comments** from X or Reddit without logging in, and **X gives only 5–6 posts of a user's history**. Reddit histories work well (100+ comments per user, structured).
2. On a Cresci subset, **266 of 377 humans (71%) are flagged**, at every confidence cut, although the same humans are never flagged on the full Cresci data. A human community that replies to and reposts each other is chained into a botnet's cluster through 52 human–bot links.
3. Flagging **members by their own copied share** instead of the cluster's confidence cuts that false-positive rate to 10% (at 0.5) while keeping recall at 98%.
4. Full Cresci on the current core: precision **1.000**, recall **0.790**, false-positive rate **0.000** at cut 0.2.

## 1. Context.dev probes

Done through the Context.dev MCP server (team account, 50,000 credits redeemed), with logged-out access as Context.dev provides it. 13 credits used in total. Only counts are reported here, not anyone's posts.

| What | X / Twitter | Reddit |
|---|---|---|
| A thread and its commenters | **No.** A post page shows the post and **3 of 250** replies, then a login wall ("See all the replies"). | **No.** The `reddit-post` parser returns the post (comment count 203) but an **empty comment list**, also with `?sort=new` and no cache. `old.reddit.com` redirects to a login page. Reported to Context.dev as feedback `fb_12cabe9f…`. The `reddit-subreddit` parser gave `WEBSITE_ACCESS_ERROR`. |
| One user's history | **5–6 posts** per profile (tested on two ordinary accounts with 8,050 and 18,300 posts), then a login wall. The replies tab is login-walled at once. Profile data (join date, total posts, followers) is readable. | **Yes.** The `reddit-user` parser returns comments with time, subreddit, parent id and the post they were left on, plus account age and karma; `limit` up to 1,000. |

Context.dev offers logged-in scraping ("browser profiles") only on a paid plan; not tried. Worth asking at their booth: is the empty Reddit comment list a bug, and do browser profiles work for X?

**What it means for B11:**
- "Turn a link into `comments.csv`" does not work yet for X or Reddit threads. A workable route: **the user saves the thread page from their own logged-in browser** (or pastes it), the website reads the commenters from that HTML, and Context.dev fetches their histories.
- **~15 comments of history per commenter is possible on Reddit, not on X** (5–6). Test A's rerun found 3–5 comments per account inside one window at recall 0.28–0.73, but 10–20 at 0–0.05; so 5–6 X posts may land in the better range by accident, and ~15 Reddit comments in the worse one, until the chance-test issue in Test A is fixed.
- Cost: about 1 credit per history; a thread of 200 commenters is about 200 credits.

## 2. A Cresci subset flags most humans

`AllComments_Combined.csv`, a file shared within the team: 3,574,246 tweets from 4,905 accounts, already in the standard comments format with screen names. Every account matches a Cresci 2017 screen name, so it is a **Cresci subset** (research-only licence; kept in `data/raw/`, never committed or served). Its make-up: 3,457 social 2, 742 social 1, 329 social 3, **377 human** (of Cresci's 1,083). Labels were joined from Cresci's `users.csv` only to measure.

| Data | Precision | Recall | False-positive rate |
|---|---|---|---|
| This subset | 0.944 | 0.989 | **0.706** (266 of 377 humans), the same at every cut from 0 to 0.5 |
| Full Cresci, same core | **1.000** | **0.790** | **0.000** (none of the same 266 humans flagged) |

The 266 humans have the same tweets in both files (median 3,196 each). **Whether a person is flagged depends on who else is in the file.** For the product that is the dangerous case: what a user uploads, or what we scrape, is an arbitrary mix.

The precision of 0.944 looks fine only because 92% of the accounts in this file are bots.

### Why: a human community chained into a botnet

All 266 humans sit in one cluster with 727 social-1 bots (999 accounts, confidence 0.794). The links of the whole file:

| Pair | text | repost | reply |
|---|---|---|---|
| bot–bot | 1,306,763 | 43,637 | 736 |
| **human–human** | 0 | **1,442** | **5,378** |
| **human–bot** | 0 | **15** | **37** |

- The humans form a **real community**: they reply to and repost each other. That is ordinary social behaviour, and their shared content is about a third of what they post (median own copied share 0.32; bots 0.97).
- Only **35 humans** have a direct link to a bot (52 links, all replies or reposts).
- Clusters are connected components, so those 52 links merge the whole human community into the botnet's cluster, and the members inherit its confidence of 0.794.
- It is **not** the bots' political content: flagged humans and social-1 bots share only 44 distinct texts (16% of them retweets), and under 0.1% of the humans' posts are also posted by those bots. Recurring social content among humans themselves (reposts, replies) is what links them, and a few bridges do the rest.
- It is **not** the long-text rule either: the core of `65e1ed1` (before the rule) gives exactly the same numbers.

The design already names real communities as a look-alike ("One group of 122 humans stays linked through shared retweets and replies"); the confidence cut handles it on the full data. Here a community is bridged into a botnet, and the cluster-level confidence cannot separate them.

### Flagging members, not clusters

Using each member's own `copied_share` (already in the result) instead of the cluster's confidence, on the same run:

| Flag a member when its own copied share is at least | Precision | Recall | False-positive rate | Humans flagged |
|---|---|---|---|---|
| (cluster confidence 0.2, today) | 0.944 | 0.989 | 0.706 | 266 |
| 0.3 | 0.968 | 0.983 | 0.393 | 148 |
| 0.4 | 0.981 | 0.982 | 0.228 | 86 |
| **0.5** | **0.992** | **0.981** | **0.101** | 38 |
| 0.6 | 0.996 | 0.927 | 0.045 | 17 |
| 0.7 | 0.995 | 0.277 | 0.016 | 6 |

The cuts were chosen with the labels visible, so these numbers are optimistic. It helps a lot but does not solve the root cause.

## Suggestions for the backend (the owner decides)

1. **Flag members, not whole clusters:** a member counts as flagged only when its own copied share passes a cut. Show the cluster, but list low-share members as "linked, not flagged".
2. **Do not let a few bridges merge a community into a swarm:** for example, cut clusters at weak bridges (few links between two dense parts), or require a minimum share of shared items for a member to join.
3. **Test for composition dependence:** run the same accounts with different backgrounds (full Cresci, this subset, Test A windows) and check that a given account's verdict does not flip. It belongs next to the other look-alike tests.
4. **Keep Test A's chance-test issue in view:** with 10–20 comments per account in one window a large botnet disappears; see `docs/test-a-conversation.md`.

## Reproduce

- Context.dev: `web-scrape` with `formats.markdown` or `formats.json` on an x.com profile and post URL; `formats.parse` with the prebuilt parsers `reddit-post` and `reddit-user`.
- Subset: `python -m swarm comments.csv --profiles profiles.csv --out result.json`, where `profiles.csv` has `username,label,created_at` joined from Cresci's `users.csv` by `screen_name`. The link table comes from `swarm.load.load()` and `swarm.detect.detect()` on one connection (`select u1, u2, kind, shared from link`).
