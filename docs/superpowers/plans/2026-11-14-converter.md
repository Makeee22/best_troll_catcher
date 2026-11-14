# Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a raw bundle (or a saved page) into `comments.csv` + `profiles.csv` in the standard format, for Reddit and Context.dev's review and comment parsers (approach A) and schema.org markup (approach B).

**Architecture:** Each source (a Context.dev `parsed` output, a site's HTML, schema.org markup, a history) becomes plain row dicts. One merge step drops anonymous authors and text-less rows, recognises the same comment arriving from two sources (the id mismatch), and writes the CSV files. The core does not change.

**Tech Stack:** Python 3.12 standard library only (`json`, `csv`, `html.parser`, `re`, `datetime`). pytest.

**Spec:** `docs/collect-interface.md` (the "Converter design" section and the raw bundle).

## Global Constraints

- Standard library only, and no network access in `backend/swarm/convert.py`, `sites.py` and `schemaorg.py`.
- Text is copied exactly from the source: no language model writes or rewrites rows.
- Test fixtures are hand-written and marked synthetic: no real people's comments in the repo.
- The output columns are exactly those in `docs/api.md` "Input files". Comments: `comment_id, username, text, timestamp, parent_id, thread_id`. Profiles: `username, display_name, created_at, post_count`.
- Times in the output are ISO 8601 UTC with a `Z` (`2026-11-14T10:00:00Z`), or empty.

## Row shape (shared by every task)

A comment row is a `dict` with the keys `comment_id, username, display_name, text, timestamp, parent_id, thread_id, source`. `source` is `"thread"` or `"history"`; `display_name` is used only for profiles. A profile row is a `dict` with the keys `username, display_name, created_at, post_count`. Missing values are `""`.

## Solving the id mismatch

Context.dev's `reddit-user` histories gave 13-character ids (`19ruo33ofgh8i`). A thread page may carry other ids (the parser's example: `oq7lyly`). So `merge()` matches on content instead of trusting ids:
1. Ids lose a Reddit type prefix (`t1_`, `t3_`).
2. Same `comment_id`: the first row is kept, with thread rows ahead of history rows.
3. A history row with a new id but the same `username` (case-insensitive) and the same text (whitespace collapsed, case-folded) as a thread row is that thread comment when the two times are at most 120 s apart, or when either time is missing and the pair is the only one with that key. Its id becomes an alias of the thread row's id, and the history row is dropped.
4. Every `parent_id` is rewritten through the alias map, so a history reply points at the thread comment.

## Review Focus

1. A placeholder author ("Verified User in Computer Software", "A Google user", "[deleted]") would turn many people into one account and make a false swarm: drop it and count it (Task 1).
2. A rating-only review (Google Maps reviews without `snippet`) has no text: drop it and count it, without crashing on the missing key (Tasks 1 and 2).
3. Sites with display names only (App Store, Google Play, G2) can merge two people who share a name: a warning says so (Task 2).
4. A bundle with no recognised source must give a clear error, not empty CSV files that the core rejects later (Task 1).
5. A reply that quotes its parent (`<blockquote>` in Reddit HTML) would look like a copy of the parent: strip the quote (Task 3).

---

### Task 1: The merge, the cleaning, the CSV writer and the command line

**Files:**
- Create: `backend/swarm/convert.py`
- Test: `backend/test_convert.py`

**Interfaces:**
- Produces:
  - `iso_utc(value: str | int | float | None) -> str`
  - `is_anonymous(name: str) -> bool`
  - `merge(rows: list[dict], profiles: list[dict]) -> tuple[list[dict], list[dict], list[str]]` returns comments, profiles and warnings.
  - `convert(bundle: dict) -> tuple[list[dict], list[dict], list[str]]`
  - `write(bundle_or_path: dict | str, out_dir: str) -> tuple[str, str | None, list[str]]` returns the comments path, the profiles path (or `None`) and the warnings.
  - `class ConvertError(ValueError)`
  - CLI: `python -m swarm.convert INPUT OUT_DIR`, where INPUT is a bundle `.json` or a saved `.html` page.
- Consumes (stubs until Tasks 2–4): `sites.from_parsed(parsed: dict, page_url: str) -> tuple[list[dict], list[dict], list[str]]`, `sites.from_html(html: str, page_url: str)` (same return), `schemaorg.from_html(html: str, page_url: str) -> list[dict]`.

`convert()` reads, for each page and frame:
1. `parsed`, when present;
2. else `sites.from_html`;
3. else `schemaorg.from_html`.

It then adds `histories[].items` (`id, text, timestamp, parent_id, thread_id`; status `failed` is skipped) as history rows, and their `created_at` as profiles. Coverage notes become warnings. If no rows come out of any source, it raises `ConvertError("no comments found in …")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_iso_utc_forms():
    assert iso_utc("2026-06-07T04:24:13.731000+0000") == "2026-06-07T04:24:13Z"
    assert iso_utc("2026-11-14T12:00:00+02:00") == "2026-11-14T10:00:00Z"
    assert iso_utc("2 hours ago") == "" and iso_utc(None) == ""
    assert iso_utc(1763114400) == "2025-11-14T10:00:00Z"

def test_placeholder_authors_are_anonymous():
    for name in ("", "[deleted]", "Anonymous", "Guest", "nimetön", "A Google user", "Verified User in Computer Software", "AutoModerator"):
        assert is_anonymous(name)
    assert not is_anonymous("verified_fan") and not is_anonymous("guestrin")

def test_history_copy_of_a_thread_comment_is_one_comment_and_replies_follow_it():
    # synthetic rows
    thread = row("oq7lyly", "alice", "Hello  world", "2026-11-14T10:00:00Z", source="thread")
    copy = row("19ruo33ofgh8i", "Alice", "hello world", "2026-11-14T10:00:30Z", source="history")
    reply = row("19ruzzz", "bob", "reply", "2026-11-14T10:05:00Z", parent="t1_19ruo33ofgh8i", source="history")
    later = row("19ruyyy", "alice", "Hello world", "2026-11-16T10:00:00Z", source="history")
    comments, _, _ = merge([thread, copy, reply, later], [])
    ids = [c["comment_id"] for c in comments]
    assert ids == ["oq7lyly", "19ruzzz", "19ruyyy"]
    assert comments[1]["parent_id"] == "oq7lyly"

def test_merge_drops_and_counts_anonymous_and_empty():
    comments, _, warnings = merge([row("1", "[deleted]", "x"), row("2", "carol", ""), row("3", "dave", "hi")], [])
    assert [c["username"] for c in comments] == ["dave"]
    assert any("1 comment by an anonymous" in w for w in warnings) and any("1 without text" in w for w in warnings)

def test_bundle_without_any_source_is_an_error():
    with pytest.raises(ConvertError, match="no comments found"):
        convert({"url": "https://example.com", "pages": [{"url": "https://example.com", "role": "thread", "html": "<p>hi</p>"}]})

def test_cli_writes_both_files_from_a_bundle_with_histories(tmp_path):
    # bundle: one history with two items and created_at
    ...  # asserts: header row equals the Global Constraints columns, 2 comment rows, 1 profile row, exit code 0
```

- [ ] **Step 2:** `cd backend && .venv/bin/python -m pytest -q test_convert.py`. Expected: FAIL (no module `swarm.convert`).
- [ ] **Step 3:** Implement `convert.py`.
  - Each `merge` warning reads `"converter: left out N comments by an anonymous or placeholder author"` or `"converter: left out N without text"`.
  - `is_anonymous` uses an exact set plus a prefix regex: `^(verified user|a google user|anonymous|guest)\b`.
  - Profiles are deduped by username (case-insensitive), keeping the first non-empty value of each field.
- [ ] **Step 4:** Run the tests again. Expected: PASS.
- [ ] **Step 5:** Commit `backend/swarm/convert.py`, `backend/swarm/sites.py` and `backend/swarm/schemaorg.py` (the stubs) and `backend/test_convert.py`.

### Task 2: Context.dev parser mappers

**Files:**
- Create: `backend/swarm/sites.py`
- Test: `backend/test_sites.py`

**Interfaces:**
- Produces: `from_parsed(parsed: dict, page_url: str) -> tuple[list[dict], list[dict], list[str]]`, dispatched on `parsed["type"]`. An unknown type gives `([], [], ["converter: no mapper for parser X"])`. A `parsed` with `success` false gives a warning.

| Parser | username | display_name | text | timestamp | thread_id | profile |
|---|---|---|---|---|---|---|
| `reddit-user` (source `history`) | `user.username` | | `body` | `posted_at` | `post.id` | `created_at` from `user.created_at` |
| `google-maps-reviews` | `contrib/(\d+)` from `user.link`, else `user.name` | `user.name` | `snippet` | `isoDate` | `featureId` or `cid` | `post_count` = `user.reviews` |
| `app-store-reviews` | `author` | `author` | `title + "\n" + text` | `created_at` | `app_id` | |
| `google-play-reviews` | `author` | `author` | `text` | `created_at` | `app_id` | |
| `tripadvisor-reviews` | `author.username`, else `author.id` | `author.name` | `title + "\n" + text` | `published_at` | `location.id` | `post_count` = `author.contribution_count` |
| `yelp-reviews` | `author.id` | `author.name` | `text` | `updated_at` | `business.id` | `post_count` = `author.review_count` |
| `g2-reviews` | `reviewer.name` | `reviewer.name` | `likes`, `dislikes`, `problems_solved` joined by `"\n"`, empty parts skipped | `published_at` | `product.slug` | |
| `tiktok-comments` | `author.username` | `author.nickname` | `text` | `posted_at` | from the page URL `/video/(\d+)` | |

- `comment_id` is the item's `id` in every row.
- For `reddit-user`, `parent_id` is `parent_id`; the merge strips `t1_`.
- `app-store-reviews`, `google-play-reviews` and `g2-reviews` add the warning `"converter: <parser> gives display names only: two people with the same name count as one account"`.
- A missing key never raises: `.get` with `""`.

- [ ] **Step 1: Write the failing tests:** one test per parser with a hand-written 2-item `data` dict in the shapes above.
  - Each asserts the mapped `username`, `text`, `timestamp` and `thread_id` of item 1.
  - Maps: one item without `snippet` gives text `""`.
  - G2: a `"Verified User in Computer Software"` reviewer is still mapped; the merge drops it.
  - Display-name parsers: assert the warning.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement one small function per parser and a dict `MAPPERS = {type: fn}`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit.

### Task 3: Reddit thread HTML adapter

**Files:**
- Modify: `backend/swarm/sites.py`, a port of `frontend/api/reddit_html.py`'s parser. The front-end copy stays until Makeee22 switches to the converter.
- Test: `backend/test_sites.py`

**Interfaces:**
- Produces: `from_html(html: str, page_url: str) -> tuple[list[dict], list[dict], list[str]]`. It returns `([], [], [])` when the page has no `<shreddit-comment>` or `<shreddit-post>`.
  - Rows have source `thread`.
  - The post becomes a row too when it has a body: `comment_id` = post id, `thread_id` = post id.
  - Coverage warning: `"converter: read N of M comments on the Reddit thread (the rest were not loaded on the saved page)"` when M > N.

- [ ] **Step 1: Write the failing tests:** a hand-written synthetic page with one `shreddit-post` (comment-count 5) and three comments. One is a reply whose text contains `<blockquote>quoted parent</blockquote>my answer`.
  - Ids lose their `t1_` / `t3_` prefix.
  - The reply's text is `"my answer"`.
  - The reply's `parent_id` is the parent's id.
  - The coverage warning says `3 of 5`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Port the parser; add a blockquote depth counter that skips data inside `blockquote`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit.

### Task 4: schema.org reader (B)

**Files:**
- Create (replacing the stub): `backend/swarm/schemaorg.py`
- Test: `backend/test_schemaorg.py`

**Interfaces:**
- Produces: `from_html(html: str, page_url: str) -> list[dict]` (thread rows).

**Sources it reads:**
- Every `<script type="application/ld+json">`, including `@graph` lists and nested `comment` / `review` arrays and replies.
- Microdata `itemtype` ending in `/Comment` or `/Review`, with the props `author` (nested `name`), `text` / `reviewBody`, `dateCreated` / `datePublished`.

**Fields:**
- Author: `author.url` or `author.identifier` is the username when present, else `author.name`.
- `comment_id`: `@id` or `url` or `identifier`, else a stable `f"sx{n}"` in document order.
- `parent_id`: the enclosing Comment's id for nested replies.
- `thread_id`: the enclosing `DiscussionForumPosting` / `Article` / product's `@id` or `url`, else `page_url`.

Bad JSON in one script block is skipped and never stops the others.

- [ ] **Step 1: Write the failing tests:**
  - A synthetic JSON-LD `DiscussionForumPosting` with two comments, one holding a nested reply. Assert 3 rows, the reply's `parent_id` and the author-url usernames.
  - A synthetic microdata `Review` list: 2 rows, `reviewBody` text.
  - A page with broken JSON in one block and a valid block: rows from the valid one.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the JSON-LD walk (recursive over dicts and lists), and microdata with an `HTMLParser` that keeps a stack of open item scopes.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit.

### Task 5: Check on scraped data, docs, merge

**Files:**
- Modify: `docs/collect-interface.md` (Convert: interface, id matching, status table), `CLAUDE.md` (commands, architecture line), `PLAN.md` (backend status).

- [ ] **Step 1:** For each Context.dev sample in the scratchpad `collect/`, build a one-page bundle and convert it. Then compare:
  - The number of parsed items against the output rows plus the counted drops; they must be equal.
  - Three random items field by field against their output row: text byte-equal after the merge's join, timestamp equal after `iso_utc`.
  - Print only counts and equal / not equal, never content.
- [ ] **Step 2:** Run `analyze()` on each output and record the clusters (expected few or none). The planted-swarm benchmark is not needed, because detection is unchanged.
- [ ] **Step 3:** The whole suite: `.venv/bin/python -m pytest -q`. Expected: all pass.
- [ ] **Step 4:** Update the docs; commit; merge `arde/convert` into `main` with `git pull --rebase` first, and push only when the user asks.
