# Collection: from a link to the core

How `swarm.collect` turns a link into a **raw bundle**, and how `swarm.convert` turns a bundle (or a page saved in a
browser) into the core's two CSV files. The collector needs network access; the core (`analyze()`) never imports it
and stays offline (a test checks this).

Given a link, the collector fetches as much of the discussion as can be had without logging in: the thread, each
commenter's public posts from around the thread's date where the site has them, and an honest note of what could
**not** be fetched (`coverage.notes`, which reach the result's `warnings`, and `result.collection` /
`diagnostics.reasons`). Never a way around a login wall or a site's terms.

## Python and command line

```python
from swarm.collect import collect, run, analyse, CollectError

bundle = collect(url, history=25, max_participants=None, on_progress=None, client=None)   # the raw bundle
result, bundle = run(url, similar_text=True, history=25)    # collect -> swarm.convert -> swarm.core.analyze
result = analyse(bundle, work_dir)                          # convert + analyse a bundle you already have
```

```bash
python -m swarm.collect URL OUT_DIR [--history N] [--max-participants N] [--no-similar-text]
# writes bundle.json, comments.csv, profiles.csv (when there are profiles) and result.json; prints the core's summary
python -m swarm.convert BUNDLE.json|PAGE.html OUT_DIR    # a bundle or a saved page -> the two CSV files
```

- `history` (1–100, default 25): posts kept per participant. `max_participants`: whose history is fetched, the most
  active in the thread first; `None` takes the site's own cap (500 where histories are free, 150 on Reddit).
- `on_progress(done, total)` is called after each history. `client` defaults to `ContextDev.from_env()`.
- Keys, from the environment only, never written to a bundle or a result: `CONTEXT_DEV_API_KEY` (Reddit, the review
  and comment parsers, any other page; Bluesky's thread and profiles when present), `YOUTUBE_API_KEY` (YouTube).
  `CONTEXT_DEV_WORKERS` sets Context.dev's concurrent requests (default 2).
- Errors are `CollectError` (a `ValueError`) with a message for the user: unsupported page, post not found, no key, no
  credits or quota, a site answering with something else than expected. If the similar-text model cannot be loaded,
  `run()` and `analyse()` repeat the analysis without that signal and add a warning. The command line prints errors
  as one `error: …` line and exits with 2.
- The bundle's `thread` summary (`platform`, `label`, `title`, `post_id`, `commenters`, `commenters_fetched`,
  `history_per_commenter`, `histories_ok`, `histories_failed`) and its `coverage` are copied into the result as
  `collection` (`docs/api.md`).

## Sites

Histories are taken from **the thread's date ±7 days** where the site allows it (the newest posts when nothing falls
in the window), so an old thread is judged on what its participants did then.

| Link | Thread | Histories | Key |
|---|---|---|---|
| Bluesky `bsky.app/profile/NAME/post/ID` | `getPostThread` (depth 1000). On a heated thread the public API served 195 of the root's 748 direct replies; no public endpoint returns the rest, and the gap is reported | `getAuthorFeed` (`posts_with_replies`) paged back to the thread's date (at most 5 × 100), the posts nearest it kept; `getProfiles` (25 per call) | no |
| Hacker News `news.ycombinator.com/item?id=N` | Algolia `items/N`, the whole tree | Algolia `search_by_date?tags=comment,author_NAME&numericFilters=created_at_i…` within ±7 days | no |
| Reddit `reddit.com/r/…/comments/ID` | the rendered page through Context.dev: what Reddit shows before "load more" (about 25 comments) | Context.dev `reddit-user` parser, newest comments | Context.dev |
| YouTube `youtube.com/watch?v=ID`, `youtu.be/ID`, `/shorts/ID`, `/live/ID` | Data API v3: `commentThreads` newest first (at most 2,000), replies beyond the 5 inline ones from `comments?parentId` | the API cannot list one account's comments: the channel's comment threads on all its videos (at most 1,000) stand in; channel creation dates. About 130 of the 10,000 daily quota units per link | YouTube |
| Mastodon, any server, `SERVER/@NAME/ID` | `statuses/ID` and `/context`. A server shows only the replies it has received from other servers | `accounts/ID/statuses` (40 per page, paged back to the thread's date) | no |
| Discourse, any forum, `FORUM/t/SLUG/ID` | `t/ID.json`, the posts beyond the first 20 from `t/ID/posts.json` (at most 3,000) | `user_actions.json?filter=4,5` paged back to the topic's date; `excerpt` is cut at about 300 characters | no |
| Google Maps place, App Store, Google Play, Tripadvisor, Yelp, G2, TikTok video | Context.dev's prebuilt parser (Google Maps with `limit` 200; the others one page) | none | Context.dev |
| **Any other page** with schema.org `Comment`, `Answer`, `Review` or `DiscussionForumPosting` markup (XenForo, Invision, Discourse, many news and Q&A sites) | the page rendered by Context.dev, read from its JSON-LD or microdata (the fuller one wins) | none; one page only | Context.dev |

A page without such markup raises `CollectError("This site is not supported yet: …")`. Usernames: Mastodon
`name@server`, YouTube the channel id, Discourse the forum's own; Discourse parent ids are `TOPIC#N`, so a topic and a
poster's activity agree. Not collected: likes, quote posts, followers lists. X / Twitter, Threads, Facebook and
Instagram are not supported: they need a login or a paid API.

## The raw bundle

A JSON object, one per collected link. Every field except `url` and `pages` may be missing.

```json
{
  "url": "https://news.ycombinator.com/item?id=1",
  "site": "hackernews",
  "collected_at": "2026-11-14T15:40:00Z",
  "pages": [
    {"url": "https://hn.algolia.com/api/v1/items/1", "role": "thread", "json": {"id": 1, "children": []}},
    {"url": "https://example.test/page", "role": "thread", "html": "<!doctype html>…",
     "parsed": {"type": "reddit-post", "data": {}}, "frames": [{"url": "…", "html": "…"}]}
  ],
  "histories": [
    {"username": "someone", "status": "ok", "created_at": "2015-01-01T00:00:00Z",
     "items": [{"id": "abc", "text": "…", "timestamp": "2026-11-14T10:00:00Z", "parent_id": "def", "thread_id": "x"}]}
  ],
  "coverage": {"comments_found": 25, "comments_expected": 196, "notes": ["…"]},
  "thread": {"platform": "Hacker News", "commenters": 11, "commenters_fetched": 11, "histories_ok": 11},
  "credits_used": 0
}
```

- `role`: `thread` (the discussion), `profile` (a participant's posts or profile), `more`, `frame`.
- Content goes in one of: `html` (a page), `parsed` (a Context.dev prebuilt parser's output, unchanged), `json` (a
  public API's response as a JSON value). The converter recognises `json` by its shape: Bluesky `{thread}`, `{feed}`,
  `{profiles}`; Hacker News `{id, children}`, `{hits}`; Mastodon `{status, ancestors, descendants}`, `{statuses}`;
  Discourse `{post_stream}`, `{user_actions}`; YouTube `{youtube_video, threads}`, `{youtube_threads}`,
  `{youtube_channels}`.
- `histories[]` is for histories that arrive as rows (`status`: `ok`, `suspended`, `failed`).
- Strings are UTF-8, times ISO 8601; no API key or cookie appears anywhere in a bundle.

## The converter

`swarm.convert` (standard library only, no network): `convert(bundle)` returns `(comment_rows, profile_rows,
warnings)`; `write(bundle_or_path, out_dir)` writes `comments.csv` and, when there is profile data, `profiles.csv`.

- **Each page is read in this order:** a Context.dev `parsed` output when a mapper exists for its type; a public API
  `json` response; a site's own HTML (Reddit's `<shreddit-comment>`); schema.org markup in the page and its frames.
- **Cleaning, because each of these would otherwise make false swarms:** anonymous and removed authors are dropped
  and counted (`[deleted]`, "Anonymous", "Guest", "nimetön", "vieras"); quoted parent text is stripped from replies;
  a comment seen in both the thread and a history is kept once; on the post's own server, mention, hashtag and
  user-page links are not shared links; a handle or profile URL is used before a display name.
- Only exact text is used. No language model writes rows: Context.dev's model-based extraction miscounted a thread
  (45 replies reported, 157 real), so it is used for nothing structural.
- Times become ISO UTC; relative times ("2 hours ago") become empty. `ConvertError` carries a message for the user.
- Tests use small hand-written fixtures; no real people's comments are in the repository.
