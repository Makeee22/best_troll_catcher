# Use case: spotting a propaganda swarm in a discussion

For the pitch, the video and the demo (J0l3s). Everything here is what the live site does today
(https://swarm.srv2159299.hstgr.cloud); numbers are the measured ones in `PLAN.md`, Results.

## The problem in one paragraph

Propaganda online rarely comes from one loud account. It comes from **many accounts that act as one**: they post the
same message, push the same link, repost each other and pile into the same threads, so a narrative looks like
grassroots opinion. Each account on its own can look normal: an ordinary name, a few hobby posts, a plausible age.
What gives them away is **what they share with each other**. A moderator or journalist reading one thread cannot see
that; they would have to open every participant's history and compare them by hand.

## Who uses it

| User | Question they bring |
|---|---|
| **Moderator** of a subreddit or community | "This thread filled up with the same talking point in an hour. Real users, or a brigade?" |
| **Journalist / fact-checker** | "This narrative is trending under a politician's post. Is it organic, or pushed by a network?" |
| **Researcher / trust-and-safety analyst** | "We have a dump of comments. Which accounts move together, and how sure can we be?" |

## The flow (what the user does)

1. **Paste a link** to the discussion: a Bluesky post, a Reddit thread or a Hacker News story. (A Reddit page saved
   from the browser gives more comments; a CSV of any platform's comments works too.)
2. **The site collects** the thread and every participant's newest public posts (25–30 each, up to 150 participants)
   through Context.dev and public APIs. No login, public data only.
3. **The core compares everyone with everyone**: same text, nearly the same (reworded) text, same link, same reposted
   or replied-to post. A pair of accounts is linked only if they share more than chance explains; linked accounts form
   a **swarm** with a confidence and its evidence. No language model decides anything here.
4. **The user reads the evidence**, per swarm:
   - which accounts are **flagged**, and which are **only linked** (real people who happened to share one item are
     shown apart and not accused);
   - **what they share most**: the exact message, link or post, how many members, first and last time seen;
   - **how fast copies follow each other** (seconds = automation or a scheduled campaign);
   - **accounts created together** (within 30 days) and accounts that **say they are automated**;
   - a **graph** of who is linked to whom.
5. **"Explain this swarm with AI"** (optional): a language model reads only that evidence, with usernames replaced by
   "Member 1…", and writes in plain language what the group *appears* to do (push a narrative, amplify a link…). It
   must cite the evidence, weigh innocent explanations, and give no verdict. A **news check** (Context.dev news search)
   tells whether the shared message was simply real breaking news that everyone posted.
6. **Act on it**: the result has a private link (deleted after 3 hours) to send to a moderator or editor, who checks the
   flagged accounts and decides. The tool gives a lead with evidence, never a ban list.

## Example story for the demo (synthetic data, say so on screen)

> A moderator sees a local-politics discussion where the same replies about the council, roads and the budget keep
> appearing under different people's posts. They run the analysis.
> The site finds a **swarm of 8 accounts**: all 8 posted the **same 6 replies** word for word, each copy followed
> the previous one after a median of **under 4 seconds**, and **all 8 accounts were created within one 30-day
> window**. Next to it, a 3-account group shares news headlines with a "WIRE:" prefix: the look-alike of an
> automated news feed, which the evidence lets the moderator tell apart. The AI explanation says the 8-account group
> *appears to be pushing one message*, cites the identical texts and the seconds-long gaps, and weighs innocent
> explanations (a real campaign, a common phrase) without giving a verdict.

Use the **synthetic demo** on the site for this (it opens by default and is labelled synthetic; the news check is
skipped on synthetic data). No real thread we tested contained a swarm, which is itself the honest result for
ordinary discussions. To show *linked, not flagged* members, use the numbers from the Cresci subset row (160 of the
266 bridged humans no longer flagged), not a screenshot of real accounts.

## Why judges can trust it (measured, labels used only to measure)

| Test | Result |
|---|---|
| Full Cresci 2017 bot dataset (real bot networks vs 1,083 genuine accounts) | precision **1.000**, recall 0.79 (0.77 with member-level flags), **0 genuine accounts flagged** |
| Swarms of 3–20 accounts planted into a real Reddit background (simulated swarms) | **100% found**; reworded copies found with the similar-text signal; **0 real accounts flagged** in 20 scenarios |
| Hard case: a human community bridged into a botnet (Cresci subset) | false-positive rate cut from 0.706 to **0.281** by member-level flags |

The confidence cut is the one value chosen with the labels visible; say so wherever these numbers are shown.

## What it does not do (say it before the judges ask)

- **No verdict on a single account.** A lone bot that copies nobody in the data, or writes its own text, is not found.
  Out of scope on purpose: one account's "bot score" hits real people (very active users, new accounts), and a swarm
  gives evidence a person can check.
- **Not a judge of truth.** It finds coordination, not false claims. A real campaign of real people (a petition, a fan
  group) looks the same as a bot network; the evidence and the AI explanation say so, and a human decides.
- **Limits measured:** a very large botnet (50+ accounts) or accounts that post 30+ own posts per copied one can hide;
  community-reported Reddit bots that never share identical text are mostly missed (recall 0.14). Reddit links give
  about 25 comments (what a browser shows before "load more"); Bluesky and Hacker News give the whole thread.

## One-line versions

- **Punchline:** "Propaganda is a team sport. We find the team."
- **What it is:** paste a link to a discussion; see which accounts act as one, with the evidence, not a verdict.
