# From a URL to the core: who does what

Agreed 14.11.2026 afternoon between the backend owner (Arde1001) and the front-end + infrastructure owner (Makeee22); **changed 14.11 evening: the backend owner now owns both halves, collect and convert**, the whole path from a URL to the result JSON. The front-end owner works from the returned result on (the dashboard, explanations). This file is the contract for the raw bundle and for how the front end calls the converter; the result JSON is `docs/api.md`.

```
URL ──► [1. COLLECT: Arde1001] ──►  raw bundle  ──►  [2. CONVERT: Arde1001]  ──►  comments.csv + profiles.csv  ──►  core
         get everything the page                       site-specific parsing
         and its commenters have                       into the standard format
```

## 1. Collect (backend, `backend/swarm/collect`, built 14.11 evening)

Written first by the front-end owner in `frontend/api/` (`contextdev.py` for Reddit histories, `bluesky.py` for Bluesky threads, both live on the site). Ported to `backend/swarm/collect`, which now returns the raw bundle below instead of rows (the converter does all parsing). The front-end files stay until the site switches to the backend's collector, so nothing breaks meanwhile. The collector needs network access; the core (`analyze()`) never imports it and stays offline (a test checks it).

Given a URL, it fetches as much of the page's discussion as can be had for free and without logging in: the thread, each commenter's recent public history where the site has one, and an honest note of what could **not** be fetched (`coverage.notes`, which reach the result's `warnings`). Never a way around a login wall or a site's terms.

```python
from swarm.collect import collect, run, CollectError

bundle = collect(url, history=25, max_participants=None, on_progress=None, client=None)   # the raw bundle; None = the site's own cap (500 on free APIs, 150 on Reddit)
result, bundle = run(url, similar_text=True, history=25)    # collect -> swarm.convert -> swarm.core.analyze
```

- `on_progress(done, total)` is called after each history. `client` defaults to `ContextDev.from_env()` (key `CONTEXT_DEV_API_KEY`, never logged or put in a bundle). Hacker News and Bluesky work **without a key**: Hacker News always asks Algolia directly, Bluesky tries Context.dev first when there is a key and falls back to the public API (as `bluesky.py` did), or goes straight to it without one.
- Besides `url`, `site`, `collected_at`, `pages`, `coverage` and `credits_used` (and `credits_remaining` when Context.dev reported it), the bundle has a `thread` summary: `platform`, `label`, `title`, `post_id`, `commenters`, `commenters_fetched`, `history_per_commenter`, `histories_ok`, `histories_failed` (and site extras such as `via`, the number of requests per route). The converter ignores it; the front end can show it.
- `run` writes the two CSV files to a temporary directory, so a result's `source.comments_file` is a label such as `Bluesky thread at://did:plc:…/app.bsky.feed.post/…` or `Hacker News story 38519012`, and `warnings` start with the coverage and converter notes. `profiles.csv` is absent when the site gave no profile data.
- Errors are `CollectError` (a `ValueError`) with a message for the user: unsupported site, post not found or not public, no key for a site that needs one, credits ran out, a site that answers with something other than JSON. `collect()` and `run()` raise nothing else (`run()` turns a thread without comments or unusable data into a `CollectError`); `analyse()` called on its own may also raise `ConvertError` or `InputError`. `history` is clamped to 1–100 and `max_participants` to at least 1. If the similar-text model cannot be loaded (no download yet, no network), `run()` and `analyse()` repeat the analysis without that signal and add a warning. The command line prints it as one `error: …` line with exit code 2.
- Retry, timeout, 2 concurrent requests (`CONTEXT_DEV_WORKERS`) and the credit accounting are those of `frontend/api/contextdev.py`.

**Switching the site (for Makeee22; on `main` since 14.11 evening, `bac6acd`):**
1. `frontend/api/Dockerfile`: add `RUN python -m swarm.similar download` after `COPY backend/swarm swarm` (the ~512 MB multilingual model is fetched at build time, not on the first job; `model2vec` comes from `backend/requirements.txt`).
2. `jobs.py`: for `POST /api/jobs/url`, call `run(url, history=…, on_progress=…)` (or `collect` → `convert` → `analyze` if the job needs the stages apart); `bundle["thread"]`, `bundle["credits_used"]` and `bundle["coverage"]` fill the job's `thread`, `histories_ok/failed` and `credits_used`. Show a `CollectError` message as it is. The job shape and endpoints stay as they are.
3. The dashboard: show `accounts[].flagged` and `flagged_members` (linked but not flagged = not accused), and label `signals.created_together` as counting accounts already counted under their content kind (`docs/api.md`).
4. Please rerun the Cresci subset and Test R on this core and put the numbers in `PLAN.md` Results.

```bash
python -m swarm.collect URL OUT_DIR [--history N] [--max-participants N] [--no-similar-text]
# writes bundle.json, comments.csv, profiles.csv (when there are profiles) and result.json; prints the core's summary
```

| Site (link) | Thread | Histories | Key |
|---|---|---|---|
| Bluesky post `bsky.app/profile/NAME/post/ID` | `getPostThread` (depth 1000) as a `json` page | per participant, most active first, `getAuthorFeed` (`posts_with_replies`) fetched **directly**, paged back to the thread's date (at most 5 x 100), the `history` posts nearest it kept as `{feed}`; `getProfiles` (25 per call) through Context.dev | no |
| Hacker News `news.ycombinator.com/item?id=N` | Algolia `items/N` as a `json` page | per commenter, most active first, Algolia `search_by_date?tags=comment,author_NAME&hitsPerPage=history&numericFilters=created_at_i` within the story's date ±7 days; the newest when none fall in it; `json` pages | no |
| Reddit thread `reddit.com/r/…/comments/ID` | rendered page (`html`, retried once with a longer wait if it holds no comment) | `reddit-user` parser, `parsed` unchanged | yes |
| Google Maps place, App Store, Google Play, Tripadvisor, Yelp, G2, TikTok video | the matching Context.dev parser, `parsed` unchanged (Google Maps with `limit` 200; the others return one page) | none | yes |
| YouTube video `youtube.com/watch?v=ID`, `youtu.be/ID`, `/shorts/ID`, `/live/ID` | YouTube Data API v3 (`YOUTUBE_API_KEY`): `videos`, then `commentThreads` newest first (at most 2,000 threads), replies beyond the 5 inline ones from `comments?parentId` (at most 100 threads); one `json` page `{youtube_video, threads}` | the API cannot list one account's comments: the channel's comment threads on all its videos (`allThreadsRelatedToChannelId`, at most 1,000) stand in, `json` page `{youtube_threads}`; channel creation dates from `channels` (50 per call), `{youtube_channels}`. About 130 of the 10,000 daily quota units per link; the key is never stored in the bundle | YouTube key |
| Mastodon or compatible server `SERVER/@NAME/ID` (any server) | `statuses/ID` + `statuses/ID/context`, one `json` page `{status, ancestors, descendants}`. A server shows only the replies it has received (mastodon.social, 15.11: 52 of 126) | per participant `accounts/ID/statuses` (40 per page, paged back to the thread's date ±7 days, at most 5 pages), `json` page `{statuses}`. A remote account's posts are those this server has seen | no |
| Discourse forum `FORUM/t/SLUG/ID` (any forum) | `t/ID.json`, the posts beyond the first 20 from `t/ID/posts.json` (20 ids a call, at most 3,000 posts), one `json` page | per poster `user_actions.json?filter=4,5` (paged back to the topic's date), `json` page `{user_actions}`; `excerpt` is cut at ~300 characters | no |
| **Any other page** with schema.org `Comment` / `Answer` / `Review` / `DiscussionForumPosting` markup (XenForo, Invision, Discourse, many news and Q&A sites) | the page rendered by Context.dev (`html`), read by `schemaorg.from_html`; the fuller of JSON-LD and microdata wins (XenForo's JSON-LD holds only the opening post) | none; one page only | yes |

A page with no such markup raises `CollectError("This site is not supported yet: …")`. Usernames: Mastodon `name@server` (local accounts get the server added), Discourse the forum's own; Discourse parent ids are `TOPIC#N` so a topic and a poster's activity agree. Hacker News history uses `search_by_date` (newest first); plain `search` ranks by relevance and missed the newest comment for 2 of 6 authors in a check on 14.11.

## 2. Convert (backend, `backend/`)

Given a raw bundle, produce `comments.csv` and, when there is profile data, `profiles.csv` in the standard format (`docs/api.md`, "Input files"). One converter per site kind, plus a generic fallback. The core stays unchanged.

Done 14.11 evening: the site's Reddit jobs already call the backend's converter (`1899188`); `frontend/api/reddit_html.py` is used only for the thread's title. Bluesky rows on the site still come from `frontend/api/bluesky.py` until the front end switches to `swarm.collect`.

### How to call the converter (for the front end)

On `main` since 14.11 evening. What it reads (schema.org `Comment` / `Review` markup in a saved page too, `swarm/schemaorg.py`):

| Source | Put in the bundle as |
|---|---|
| Reddit thread page (saved or fetched) | a `thread` page with `html` |
| Reddit histories | `profile` pages with `parsed` of type `reddit-user` (example below) |
| Context.dev review and comment parsers: `google-maps-reviews`, `app-store-reviews`, `google-play-reviews`, `tripadvisor-reviews`, `yelp-reviews`, `g2-reviews`, `tiktok-comments` | a `thread` page with `parsed` exactly as Context.dev returned it |
| Bluesky `getPostThread`, `getAuthorFeed`, `getProfiles` | `json` pages, see the bundle's `json` field below. Handles that are `handle.invalid` become the DID, as in `bluesky.py` |
| Hacker News Algolia `items/{id}` and `search?tags=comment,author_NAME` | `json` pages |

Rows now also carry `links` and `repost_of`, and profiles carry `bio`; `jobs._fields` already picks them up. Placeholder authors ("Verified User…", "A Google user", `[deleted]`) are dropped and counted in the warnings, and so are rating-only reviews without text. App Store, Google Play and G2 give display names only, and a warning says that two people with one name count as one account. The API image already copies `backend/swarm`, so `from swarm.convert import …` works there.

```python
from swarm.convert import convert, write, ConvertError

# 1. The saved thread page → its comments (cleaned), to know whose histories to fetch.
thread = {"url": url, "site": "reddit", "pages": [{"url": url, "role": "thread", "html": page_text}]}
comments, _, notes = convert(thread)            # raises ConvertError when the page has no comments
authors = list(dict.fromkeys(c["username"] for c in comments))   # anonymous and [deleted] are already gone

# 2. Each history as Context.dev returned it (contextdev.reddit_history keeps the comments unchanged):
for h in histories:
    if h["status"] != "failed":
        thread["pages"].append({"url": f"https://www.reddit.com/user/{h['username']}", "role": "profile",
                                "parsed": {"type": "reddit-user", "success": True,
                                           "data": {"user": {"username": h["username"], "created_at": h.get("created_at")},
                                                    "comments": h["comments"]}}})

# 3. Write the two files and analyse them.
comments_path, profiles_path, warnings = write(thread, work_dir)   # profiles_path is None when there are no profiles
result = analyze(comments_path, profiles_path)
result["warnings"] = warnings + result["warnings"]                 # "read 188 of 322 comments…", "left out 12 …"
```

- **What it replaces in `jobs.py`:** `reddit_html.parse_thread()` (step 1) and `contextdev.to_rows()` + `_write_csv()` (steps 2–3).
- **Reddit thread links (14.11 ~17:40, Makeee22):** `POST /api/jobs/url` now takes `reddit.com/r/…/comments/…` links too. Context.dev renders the page (`formats.html`, `waitFor` 6 s, one retry with a longer wait because Reddit sometimes answers with a bot check first); the HTML goes through `swarm.convert` exactly like a saved page. It gets what a browser shows before "load more": 25 of 31 and 25 of 475 comments in two tests. A saved page after clicking "View more comments" gives more.
- **Done 14.11 ~17:15 (Makeee22):** `jobs.py` now uses `swarm.convert` for the Reddit thread and the histories, exactly as above. `reddit_html.py` is used only for the thread's title, subreddit and comment count (attributes of `<shreddit-post>`, not affected by the bug). The post's own row from the converter is left out of "read N of M". Only columns in `swarm.load.COMMENT_COLUMNS` / `PROFILE_COLUMNS` are written, so the converter's `display_name`/`source` on comment rows do not cause warnings. Bluesky still converts in `frontend/api/bluesky.py` until `swarm.convert` has a Bluesky mapper. On the two pages saved earlier the file itself held only 25 comments, so 25 was right there; the bug hits pages with more loaded comments.
- **Bug in `frontend/api/reddit_html.py` (fixed by the switch above), for Makeee22:**
  - **What:** its parser counts open tags inside a comment's text and closes the text on the matching end tag. A void tag such as `<br>` has no end tag, so the count never reaches zero. The parser then stays "inside" that comment and swallows every later `<shreddit-comment>` on the page.
  - **Effect, measured on a real saved thread on 14.11:** 47 of the 188 comments on the page were read, so 141 commenters and their histories never reached the analysis, and one comment's text came out empty. The site's "read N of M comments" line undercounts the same way.
  - **Fix:** switch to the converter (below), which reads all 188, or skip void tags (`br`, `img`, `hr`, `input`, `wbr`) in `handle_starttag`. The backend left the file unchanged because it is in `frontend/`.
- **Why switch:** besides the bug, the converter drops anonymous and placeholder authors, strips quoted parent text from replies, and keeps a comment once when it appears in both the thread and a history. On that page it keeps 170 of the 188 comments; the rest are deleted or empty.
- **The same comment in the thread and in a history** is kept once. Replies that point at it keep working, even if the two ids differed.
- **`page_text`** is the page as a string: `raw.decode("utf-8", errors="replace")`.
- **Errors:** `ConvertError` (a `ValueError`) has a message to show the user as it is.
- **Command line:** `python -m swarm.convert page.html OUT_DIR` or `python -m swarm.convert bundle.json OUT_DIR`. Warnings go to stderr, and the exit code is 2 on an error.

### Converter design

Approved by the backend owner on 14.11 at about 18:00; built the same evening (on `main`: Reddit, the Context.dev parsers, Bluesky, Hacker News and schema.org). It covers approaches A (site adapters) and B (schema.org markup); C (a generic repeated-block fallback) is an extra if time is left.

- **One module, `backend/swarm/convert.py`:** standard library only, with no network access.
  - `convert(bundle)` returns `(comment_rows, profile_rows, warnings)`.
  - `python -m swarm.convert BUNDLE.json|PAGE.html OUT_DIR` writes the two CSV files. A saved page works without a bundle, so a local user can convert a page they saved themselves.
- **Each page is read in this order:**
  1. **Context.dev `parsed` output** when a mapper exists for its `type`. First Reddit; then the review parsers (Google Maps, App Store, Google Play, Tripadvisor, Yelp, G2).
  2. **A site adapter that recognises the HTML.** First Reddit's `<shreddit-comment>`, moved over from `frontend/api/reddit_html.py`.
  3. **schema.org `Comment` / `Review` / `DiscussionForumPosting` data** (JSON-LD or microdata) in the page and its `frames`.
- **Then:**
  - `histories[].items` become rows; `created_at` goes to `profiles.csv`.
  - Duplicates are dropped by `comment_id`.
- **Shared cleaning, because each of these would otherwise make false swarms:**
  - Anonymous or removed authors are dropped and counted: `[deleted]`, "Anonymous", "Guest", "nimetön", "vieras".
  - Quoted parent text (`blockquote`) is stripped from replies.
  - Only exact text is used. No language model writes rows, so Context.dev's AI `json` format is not used for comments.
  - Times become ISO UTC; relative times ("2 hours ago") become empty.
  - A handle or profile URL is used before a display name, because two people can share a display name.
- **Warnings:** `coverage` and the cleaning counts come back as warnings, which the front end adds to the result's `warnings`.
- **Tests:** small hand-written fixture pages, marked synthetic. No real people's comments go into the repo.
- **To check before building:**
  - **Ids may not match between thread and history.** On 14.11 the `reddit-user` parser returned 13-character comment and parent ids (all starting `19r`), while a thread page has Reddit's 7-character ids (`oq7lyly`). If they really differ, a thread comment is not recognised in its author's history, and replies cannot point across the two.
  - **Raw JSON from public APIs has no field yet.** A site's public JSON API (WordPress, Discourse) has nowhere to go in a page; add a `json` field to the page when it is needed.

## The raw bundle (the handover)

A JSON object, one per collected URL. The collector fills what it has; every field except `url` and `pages` may be missing.

```json
{
  "url": "https://www.reddit.com/r/worldnews/comments/1xvzor3/...",
  "site": "reddit",
  "collected_at": "2026-11-14T15:40:00Z",
  "pages": [
    {
      "url": "https://www.reddit.com/r/worldnews/comments/1xvzor3/...",
      "role": "thread",
      "html": "<!doctype html>…",
      "markdown": "…",
      "parsed": {"type": "reddit-post", "data": {"…": "Context.dev prebuilt parser output, unchanged"}},
      "frames": [{"url": "https://disqus.com/embed/comments/…", "html": "…"}]
    }
  ],
  "histories": [
    {"username": "someone", "site": "reddit", "status": "ok",
     "created_at": "2015-01-01T00:00:00Z",
     "items": [{"id": "abc", "text": "…", "timestamp": "2026-11-14T10:00:00Z", "parent_id": "def", "thread_id": "1xvzor3"}]}
  ],
  "coverage": {"comments_found": 25, "comments_expected": 196, "notes": ["the rest are behind a 'load more' button"]},
  "credits_used": 27
}
```

- `role`: `thread` (the page the user gave), `more` (a further comment page of the same thread), `profile` (a commenter's page), `frame` (an embedded widget).
- `parsed`: Context.dev's prebuilt parser output as it came, when one exists for the site; `null` otherwise.
- `json` (added 14.11 evening for Bluesky and Hacker News): a site's public API response, **unchanged**, as a JSON value (not a string). The converter recognises it by its shape, so no site name is needed:

  | Site | Page `role: "thread"` | Page `role: "profile"`, one per commenter (histories) |
  |---|---|---|
  | Bluesky | `app.bsky.feed.getPostThread` (the whole response, `{"thread": …}`; ask for `depth` 10 or more) | `app.bsky.feed.getAuthorFeed` (`{"feed": […]}`), reposts included; `app.bsky.actor.getProfiles` (`{"profiles": […]}`) for bio, join date and post count, as its own page |
  | Hacker News | Algolia `items/{id}` (`{"id", "children": […]}`) | Algolia `search?tags=comment,author_NAME` (`{"hits": […]}`) |

  Put Bluesky and Hacker News histories here, as `profile` pages, rather than in `histories[]`. The converter maps reposts, links in Bluesky facets, and HN's HTML comment text itself.
- `histories[].status`: `ok`, `suspended`, `failed` (as in `frontend/api/contextdev.py`).
- `coverage` feeds the page's honest "read N of M comments" line and should also reach the result's `warnings`.

The converter can rely on: UTF-8 strings; times in ISO 8601 UTC; usernames as the site shows them; no API keys or cookies anywhere in the bundle.

## Status on 14.11 at 17:30

| Site | Thread comments | Commenters' histories | Notes |
|---|---|---|---|
| Reddit | Only from a page saved in the browser: whatever the browser had loaded (188 comments on the saved test page; the rest behind "load more"). Context.dev's `reddit-post` parser returns an empty comment list (reported to Context.dev). | Yes: `reddit-user` parser, 25 newest comments, about 1 credit and 0.4 s each | Live on the site as "Analyse a Reddit thread" |
| X / Twitter | 3 replies, then a login wall | 5–6 posts, then a login wall | Not usable without logging in |
| **Bluesky** | **Yes, complete:** the public API `app.bsky.feed.getPostThread` (no login, depth 1000) gives every reply the AppView serves, nested ones included. **Not every reply:** on a heated thread (15.11, handoff R1) the root counted 748 direct replies and the API served 195; nested posts were complete. `getPostThreadV2` and its hidden "other replies" return a subset of those 195, and no public endpoint pages through the rest (deleted, blocked, from removed accounts, or withheld). The sum of Bluesky's own `replyCount` over the posts we read says how many there should be; the gap is reported as `partial_thread`. | **Yes:** public `app.bsky.feed.getAuthorFeed` (fetched directly, no credits: paged back up to 5 x 100 to the thread's date, the posts nearest it kept; replies and reposts); `app.bsky.actor.getProfiles` for creation date, bio and counts, 25 accounts per call | **Done: `frontend/api/bluesky.py`, on the site as "Analyse a discussion from a link"** (`POST /api/jobs/url`). Every request goes through Context.dev (`web-scrape` with `formats.bytes`, the untouched response body; about 1 credit each) with a direct request to the same public endpoint as fallback when Context.dev does not answer in 10 s. Measured 14.11 with 2 requests at a time: 43 replies from 38 participants in 17–100 s for 42 credits; 158 replies from 143 participants in 333 s for 147 credits (Context.dev took 1.5–5 s per request then); the core ran all four signals on 4,209 rows in 1.4 s. |
| **Hacker News** | **Yes, complete:** the public Algolia API `hn.algolia.com/api/v1/items/{id}` returned all 1,124 comments from 717 commenters of one story, with `parent_id` and times | Yes: Algolia search by author (`tags=comment,author_NAME`) | Done 14.11 evening: `swarm.collect` (no key needed) |
| Others | Not tested yet | | |

### Bluesky: how the collector maps to the raw bundle

`bluesky.Bluesky(client).collect(post_url)` returns the bundle's content already as rows, because the page needs a result today. **This interim row conversion lives in `frontend/api/bluesky.py` (`_post_row`, the repost rows and the profile rows in `collect`) until the backend's converter takes over**; it then moves to the convert half like the Reddit ones.

| Raw bundle | Bluesky source | Row conversion today |
|---|---|---|
| `url`, `site: "bluesky"` | the `bsky.app/profile/NAME/post/ID` link; the handle is resolved with `com.atproto.identity.resolveHandle` | `thread.url`, `thread.post_id` (the `at://` URI) |
| `pages[0]` (`role: thread`) | `getPostThread` JSON | one comment row per post: `comment_id` = the post's `at://` URI, `username` = handle (the DID when the handle is `handle.invalid`), `timestamp` = `record.createdAt`, `text`, `links` (link facets and the external embed), `parent_id` and `thread_id` from `record.reply` |
| `histories[].items` | `getAuthorFeed` (`filter=posts_with_replies`) per participant | the participant's own posts and replies as comment rows; a **repost** becomes a row with empty text and `repost_of` = the reposted post's URI (id `repost:HANDLE:URI`, time = when it was reposted), which feeds the core's `repost` signal |
| `histories[].created_at` and profile data | `getProfiles` | `profiles.csv`: `username`, `created_at`, `display_name`, `bio`, `followers`, `following`, `post_count`, `default_avatar` |
| `coverage` | counts from the thread | `thread.comments_found`, `comments_expected` (sum of `replyCount`), `comments_hidden` (blocked or removed nodes), `commenters`, `commenters_fetched` (cap: 150 on the site), and notes at the top of the result's `warnings` |
| `credits_used` | Context.dev's `key_metadata` | the job's `credits_used`; `thread.via` counts requests through Context.dev and direct ones |

Not collected: likes, quote posts as their own signal, more than `history` (default 25) posts per participant, followers lists.

### For the converter: do not trust Context.dev's model-based extraction for counts or structure

Context.dev's `formats.json` (a model reads the page and fills a JSON schema) **miscounted** the Bluesky thread: it reported 45 replies from 45 authors, while parsing the same JSON ourselves gives 157 replies from 141 authors. Use it only to get a rough idea of a page. For the converter, parse the raw content (`html`, the JSON inside `markdown`, or `parsed` from a **prebuilt** parser, which is rule-based) yourself, and check counts against the site's own number (for example `replyCount`, `comment-count`) into `coverage`.

Measured with planted swarms on a real Reddit background (26 commenters with 25-comment histories): copying swarms of 3–20 accounts are all found, reworded ones too with `--similar-text` after `c759a49`, and no real commenter is flagged. Details: `docs/findings-context-dev-and-subset.md`.
