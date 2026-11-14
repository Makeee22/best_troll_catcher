# From a URL to the core: who does what

Agreed 14.11.2026 afternoon between the backend owner (Arde1001) and the front-end + infrastructure owner (Makeee22). This file is the contract between the two halves, like `docs/api.md` is between the API and the page. Change it together.

```
URL ──► [1. COLLECT: Makeee22]  ──►  raw bundle  ──►  [2. CONVERT: Arde1001]  ──►  comments.csv + profiles.csv  ──►  core
         get everything the page                       site-specific parsing
         and its commenters have                       into the standard format
```

## 1. Collect (front end + infrastructure, `frontend/api/`)

Given a URL, fetch as much of the page's discussion as can be had for free and without logging in:

- the page itself, rendered (JavaScript included), with embedded comment widgets (iframes) when present
- further comment pages (pagination, "more comments" endpoints) when the site offers them without a click
- each commenter's recent public history, when the site has public profile pages (Reddit: done, `frontend/api/contextdev.py`)
- an honest note of what could **not** be fetched (for example "25 of 196 comments: the rest are behind a 'load more' button")

Tools: Context.dev (`web-scrape` with JavaScript rendering, `includeFrames`, prebuilt parsers; `web-map` and `web-crawl` for linked pages), and a site's own public, login-free endpoints where it has them. Never a way around a login wall or a site's terms.

## 2. Convert (backend, `backend/`)

Given a raw bundle, produce `comments.csv` and, when there is profile data, `profiles.csv` in the standard format (`docs/api.md`, "Input files"). One converter per site kind, plus a generic fallback. The core stays unchanged.

`frontend/api/reddit_html.py` (a Reddit thread page saved from the browser → comments) and `contextdev.to_rows()` (Reddit histories → rows) were written before this split. **They belong in the converter half:** the backend owner may move or rewrite them; the front end will then call the backend's converter instead.

### How to call the converter (for the front end)

On `main` since 14.11 evening, for Reddit. The review parsers and schema.org follow. The API image already copies `backend/swarm`, so `from swarm.convert import …` works there.

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

Approved by the backend owner on 14.11 at about 18:00. It gets built after the website works end to end. It covers approaches A (site adapters) and B (schema.org markup); C (a generic repeated-block fallback) is an extra if time is left.

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
- `histories[].status`: `ok`, `suspended`, `failed` (as in `frontend/api/contextdev.py`).
- `coverage` feeds the page's honest "read N of M comments" line and should also reach the result's `warnings`.

The converter can rely on: UTF-8 strings; times in ISO 8601 UTC; usernames as the site shows them; no API keys or cookies anywhere in the bundle.

## Status on 14.11 at 17:30

| Site | Thread comments | Commenters' histories | Notes |
|---|---|---|---|
| Reddit | Only from a page saved in the browser (~25 comments; the rest behind "load more"). Context.dev's `reddit-post` parser returns an empty comment list (reported to Context.dev). | Yes: `reddit-user` parser, 25 newest comments, about 1 credit and 0.4 s each | Live on the site as "Analyse a Reddit thread" |
| X / Twitter | 3 replies, then a login wall | 5–6 posts, then a login wall | Not usable without logging in |
| **Bluesky** | **Yes, complete:** the public API `app.bsky.feed.getPostThread` (no login, depth 1000) gives every public reply, nested ones included. Replies that are deleted, hidden or blocked are missing; the sum of Bluesky's own `replyCount` over the posts we read says how many there should be. | **Yes:** public `app.bsky.feed.getAuthorFeed` (newest 30 posts, replies and reposts per participant, one request each); `app.bsky.actor.getProfiles` for creation date, bio and counts, 25 accounts per call | **Done: `frontend/api/bluesky.py`, on the site as "Analyse a discussion from a link"** (`POST /api/jobs/url`). Every request goes through Context.dev (`web-scrape` with `formats.bytes`, the untouched response body; about 1 credit each) with a direct request to the same public endpoint as fallback when Context.dev does not answer in 10 s. Measured 14.11 with 2 requests at a time: 43 replies from 38 participants in 17–100 s for 42 credits; 158 replies from 143 participants in 333 s for 147 credits (Context.dev took 1.5–5 s per request then); the core ran all four signals on 4,209 rows in 1.4 s. |
| **Hacker News** | **Yes, complete:** the public Algolia API `hn.algolia.com/api/v1/items/{id}` returned all 1,124 comments from 717 commenters of one story, with `parent_id` and times | Yes: Algolia search by author (`tags=comment,author_NAME`) | Collector next, after Bluesky |
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

Not collected: likes, quote posts as their own signal, more than the newest 30 items per participant, followers lists.

### For the converter: do not trust Context.dev's model-based extraction for counts or structure

Context.dev's `formats.json` (a model reads the page and fills a JSON schema) **miscounted** the Bluesky thread: it reported 45 replies from 45 authors, while parsing the same JSON ourselves gives 157 replies from 141 authors. Use it only to get a rough idea of a page. For the converter, parse the raw content (`html`, the JSON inside `markdown`, or `parsed` from a **prebuilt** parser, which is rule-based) yourself, and check counts against the site's own number (for example `replyCount`, `comment-count`) into `coverage`.

Measured with planted swarms on a real Reddit background (26 commenters with 25-comment histories): copying swarms of 3–20 accounts are all found, reworded ones too with `--similar-text` after `c759a49`, and no real commenter is flagged. Details: `docs/findings-context-dev-and-subset.md`.
