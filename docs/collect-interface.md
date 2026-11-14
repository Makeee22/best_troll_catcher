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

## Status on 14.11 at 15:45

| Site | Thread comments | Commenters' histories | Notes |
|---|---|---|---|
| Reddit | Only from a page saved in the browser (~25 comments; the rest behind "load more"). Context.dev's `reddit-post` parser returns an empty comment list (reported to Context.dev). | Yes: `reddit-user` parser, 25 newest comments, about 1 credit and 0.4 s each | Live on the site as "Analyse a Reddit thread" |
| X / Twitter | 3 replies, then a login wall | 5–6 posts, then a login wall | Not usable without logging in |
| Others | Not tested yet | | Next: sites whose full discussion is public without login (see `PLAN.md`) |

Measured with planted swarms on a real Reddit background (26 commenters with 25-comment histories): copying swarms of 3–20 accounts are all found, reworded ones too with `--similar-text` after `c759a49`, and no real commenter is flagged. Details: `docs/findings-context-dev-and-subset.md`.
