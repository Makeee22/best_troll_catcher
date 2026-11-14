# Test R: community-reported Reddit bots from 2026

Written 14.11.2026 (evening). Core of `main` at `1b0866f`, run unchanged. Scripts are outside the repo; the collected data is in `data/raw/reported-bots/` (ignored). This file holds aggregate numbers only: no usernames, no comment text, no links to the report posts.

**In short:** on 72 accounts that Reddit users reported as bots in May–November 2026 and that still had readable comments, the core flagged 10 (recall 0.139) and 1 of 96 background accounts (false-positive rate 0.010, precision 0.909). All 10 come from one reported network that pastes the same short phrases. In the other 15 reported networks no two co-reported accounts shared a single comment text in their newest 25 comments, so there was nothing for the core to link. The similar-text layer changed no result. The core fails safe here; it does not find most of what the community reports today.

## Question

Every benchmark so far uses Twitter bots from 2014 (Cresci), synthetic swarms, or swarms we planted ourselves. Does the core find bot networks that are active on Reddit now, in the data the website can actually collect (each account's newest 25 comments)?

## Method

1. **Report posts.** Candidates from the listing pages of a subreddit where users report suspected bot accounts (new, hot, top of week/month/year) and seven web searches restricted to that subreddit. The 60 newest candidate posts were fetched as rendered pages (Context.dev, public, no login).
2. **Reported accounts.** From each page: usernames written as `u/name` or linked as `/user/name` in the post body, in comments by the post's author, and in comments that list two or more names. Removed: the reporter, everyone who commented in the thread, moderation and helper bots. An account named in several posts counts for the newest. The accounts named in one post form one "reported network".
3. **Histories.** Each account's newest 25 comments with Context.dev's `reddit-user` parser.
4. **Background.** Reported accounts' comments from June 2026 on were grouped by subreddit. For the 16 subreddits with the most reported accounts, the thread with the most reported comments was fetched; its visible commenters who are not in the reported set (and whose name does not end in "bot") are the background. All 194 were fetched and labelled `human`.
5. **Run.** `swarm.convert.write` for the two CSV files, then `swarm.core.analyze` with labels `bot:<report post>` and `human`: rules only, and with `similar_text=True` (multilingual model). Default parameters, confidence cut 0.2. Labels were used only to measure.

## What was collected

| | Reported | Background |
|---|---|---|
| Report posts fetched / with named accounts / naming 3 or more | 60 / 29 / 15 | |
| Posts dated | May–November 2026 (15 of 29 from October–November) | |
| Accounts | 296 | 194 (from 16 threads) |
| Page gone (HTTP 404: deleted or removed) | 117 (40%) | 0 |
| No comment list returned (suspended, or history hidden by the owner; the parser cannot tell which) | 53 (18%) | 12 (6%) |
| Profile readable, 0 comments visible (posts only, comments removed, or hidden) | 51 | 85 |
| 1–2 comments | 4 | 0 |
| 3 or more comments | 71 | 97 |
| **Counted by the core (with usable content)** | **72**, in 16 networks | **96** |
| Networks with 3 or more analysable accounts | 6 (sizes 30, 17, 4, 3, 3, 3) | |

4,053 comments in total. Only a quarter of the reported accounts could be analysed at all: 57% were already gone or returned no comment list a few weeks or months after the report, which supports the reports but leaves no data.

## Results

| Variant | Precision | Recall | False-positive rate | Clusters |
|---|---|---|---|---|
| Rules only | 0.909 (10 of 11) | 0.139 (10 of 72) | 0.010 (1 of 96) | 2: 4 accounts at confidence 0.69, 7 accounts at 0.64 |
| + similar-text layer (`potion-multilingual-128M`, 16 s) | 0.909 | 0.139 | 0.010 | the same 2: 0.711 and 0.66; 22 similar-text items, 0 new links |

The numbers are the same at every cut from 0 to 0.5: there are no low-confidence clusters under the cut.

**Per reported network**

- One network (30 analysable accounts, reported for comment spam that promotes paid adult content): 10 flagged, 33%. They land in **two** clusters (4 and 6 reported accounts), not one. 15 more of its members share at least one identical text with a co-reported account but not enough to pass the test.
- The other 15 networks (42 analysable accounts, among them one with 17 and four with 3–4): 0 flagged. A direct count shows why: no account in them shares one identical comment text (3 words or more) with a co-reported account.
- No cluster mixes two reported networks.

**Evidence.** Every link is word-for-word shared text (14 text links; the reply signal gave 1 link that formed no cluster; no shared links; reposts are not in the data). The shared texts are short stock phrases of 4–7 words pasted under many posts, each used by 2–6 accounts. This is phrase reuse from a common list, not copying of other users' comments. Copies are days apart (median gap 4.7 and 9.7 days), so timing would not have found them. All members of both clusters were created within 30 days of each other.

**The one flagged background account** was created in the same 30 days as the six reported accounts in its cluster and shares 2–4 identical phrases with four of them. It is very probably an unreported member of the same network, so the true precision is likely 11 of 11. It cannot be proven from here.

## Sanity check: are the two groups comparable?

- Subreddits: reported accounts comment in 403, background accounts in 1,035, and 92 are common. 31% of the reported comments and 20% of the background comments are in common subreddits; 53 of 75 reported and 85 of 97 background accounts have at least one comment in one.
- The core never uses subreddit as a signal, so this cannot produce flags by itself. Thread and parent ids do feed the reply signal, which linked one pair.
- The groups do differ: median account age 151 days (reported) against 1,347 days (background), median comment length 4 words against 7. Much of the reported activity is in adult subreddits; 9 of the 16 background threads are too.
- Background accounts were picked from the same threads the reported accounts commented in, so the background is the bots' real surroundings, not a random sample of Reddit.

## What it means

- **Precision holds on present-day data.** 96 ordinary commenters from the same threads, 0 or 1 flagged, and the one is probably a bot. Among the background accounts only 9 share any identical text with anyone.
- **Recall is low, and mostly not because of the chance test.** The core needs groups of 3 or more that share content. Of 16 reported networks only 6 had 3 or more accounts left to analyse, and only one of those repeats text among its members within 25 comments. What the community reports in 2026 is mostly other behaviour: accounts that post images or links and hardly comment, accounts whose comments are each different (probably generated), reposts of other people's posts (submissions are not collected), single spam accounts. None of that leaves shared comment text.
- **The similar-text layer did not help** on this data: 22 near-duplicate items, no link.
- **Within the one text-sharing network** the core found a third and split it in two. With a median of 2–4 words per comment the long-text rule (10 words) never applies, so each pair needs two shared phrases.
- For the pitch: this is a real-data, present-day check of the false-positive rate, and an honest statement that the core detects copy-paste swarms and not today's wider range of bots. It agrees with "Known limits" in `docs/core-design.md` (reworded copies, loose groups, small data).

## Limits

- **Weak labels.** "Reported by a user" is not proof. Names were extracted by pattern from posts and comments; a named account may be a victim, an example or a mistake. We did not check them one by one.
- **The background is not clean.** It comes from threads where bots comment, and at least one background account looks like a bot. So the false-positive rate here is an upper estimate, and missed unreported bots in the background do not show up as errors.
- **Selection bias.** The community reports what people notice: adult-content spam, karma farming, obvious rings. Quiet coordinated accounts are not in this set. And the accounts still readable are the ones Reddit has not removed, likely the harder cases.
- **Survivorship.** 57% of the reported accounts had no readable comments. Recall is measured on the remaining quarter.
- **Small numbers.** 72 and 96 accounts; one network decides the recall. One account more or less moves precision by 0.09.
- **Shallow histories.** 25 newest comments per account, comments only. Reposted submissions and deleted comments are invisible. Visible commenters of a thread page are the first 25 or so.
- **One community, one site, one evening.** A second source of reports, or the same networks with full histories, could give different numbers.
- The status "suspended" in our collector means "the parser returned no comment list". Reddit lets users hide their history, and 6% of the background got this status too, so not all 53 are suspensions.
