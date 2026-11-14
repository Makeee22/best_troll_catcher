# Core (part 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the walking skeleton in `backend/swarm/` with the open core: two standard CSV files in, a JSON list of probably-coordinated account clusters with confidence and evidence out.

**Architecture:** One DuckDB connection per run carries the data through four stages, each a module that reads and writes named tables: `load` (CSV to `comments`, `profiles`), `detect` (to `item`, `link`, `member`, `cluster`), `evaluate` (metrics from labels), `core` (orchestration and the result document). A command line and a read-only FastAPI app are thin wrappers around `core.analyze()`.

**Tech Stack:** Python 3.12+, DuckDB 2.x, FastAPI, uvicorn, pytest. Optional: model2vec (task 8 only).

**Spec:** `docs/core-design.md`. Read it first. This plan argues from it.

## Global Constraints

- All commands run from `backend/` with the virtual environment: `.venv/bin/python -m pytest -q`.
- Work on the git branch `arde/core`. `swarm/api.py` is broken between task 2 and task 7; that is why this is a branch. Merge to `main` only when task 7 is green.
- Commit locally after each task, staging files by name (never `git add -A` or `git add .`). Do not push; the user pushes.
- Never commit anything under `backend/data/`. Never print tweet text, usernames or other content of the Cresci dataset into code, tests, docs, commit messages or logs. Aggregate numbers only.
- DuckDB 2.0 API: always `con.execute(sql, params).fetchall()`. Do not use `.fetchone()` (it leaves the connection busy) and do not call `.fetchall()` on `con.sql(...)` for anything but printing.
- DuckDB cannot hand a `TIMESTAMPTZ` to Python without `pytz`. Store times as plain `TIMESTAMP` in UTC and turn them into text in SQL with `strftime(ts, '%Y-%m-%dT%H:%M:%SZ')`.
- DuckDB's `executemany` is slow. Insert many rows with one statement (list parameters and `unnest`, or a temporary CSV).
- File paths go into SQL as query parameters (`read_csv(?, ...)`), never by string formatting.
- Regular expressions in SQL are RE2. A word is `[\p{L}\p{N}_]+`, so that non-English text works.
- No language model, no network access, no new dependency besides `duckdb` (and `pytest`, `httpx` for tests).
- Parameter defaults, copied from the spec: `MIN_WORDS = 5`, `MIN_SHARED = 2`, `ALPHA = 0.01`, `MIN_SIZE = 3`, `MIN_CONFIDENCE = 0.2`, `PAIR_BUDGET = 1_000_000_000`, at most 500 `edges` and 20 `top_items` per cluster.
- Any input column except `username` may be missing. A missing column produces a warning, never a crash.
- Synthetic data carries `synthetic = 1` on every comment.
- A comment in code only for a why the code cannot show, in one line. A known limit gets `# shortcut: <the limit>, <when to upgrade>`.

Task order: 1 and 2 are independent. 3 needs both. 4 needs 3. Then 5, 6 and 7 are independent of each other. 8 is optional and last.

## File Structure

| File | Responsibility |
|---|---|
| `backend/swarm/load.py` (new) | Read the two CSV files into tables `comments` and `profiles`; collect warnings; `InputError` |
| `backend/swarm/detect.py` (rewrite) | Items, pairs, chance test, links, clusters, copied share |
| `backend/swarm/evaluate.py` (new) | Metrics from the `label` column |
| `backend/swarm/core.py` (new) | `analyze()`: run the stages, build the result document |
| `backend/swarm/__main__.py` (new) | Command line |
| `backend/swarm/synthetic.py` (rewrite) | Simulated data in the standard format |
| `backend/swarm/cresci.py` (new) | Convert the Cresci 2017 zips to the standard format |
| `backend/swarm/api.py` (rewrite) | Read-only HTTP API serving one result |
| `backend/swarm/similar.py` (new, task 8) | Optional similar-text signal |
| `backend/conftest.py` (new) | Shared test helper `make_csv` |
| `backend/test_load.py`, `test_detect.py` (rewrite), `test_evaluate.py`, `test_core.py`, `test_cli.py`, `test_cresci.py`, `test_api.py` | One test file per module |
| `backend/requirements.txt`, `backend/requirements-dev.txt` (new) | Run-time and test dependencies |
| `docs/api.md` (rewrite), `CLAUDE.md`, `PLAN.md` | Contract and project docs |

## Review Focus

Inputs the spec implies but does not spell out, most likely first. Each has a test in the task that owns the code.

1. A semicolon-delimited CSV with a byte-order mark (what Excel exports in Finland): loads exactly like a comma file. (Task 1)
2. Comment text with line breaks, commas and quotes inside a quoted cell: stays one row. (Task 1)
3. One account repeating its own text many times: one item, no link, no cluster. (Task 3)
4. Emoji-only, punctuation-only and whitespace-only comments: no item, no crash. (Task 3)
5. A file path with a space and a quote in it: loads. (Task 1)

---

### Task 1: Loading the standard CSV files

**Files:**
- Create: `backend/swarm/load.py`, `backend/conftest.py`, `backend/test_load.py`, `backend/requirements-dev.txt`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces:
  - `COMMENT_COLUMNS = ["comment_id", "username", "timestamp", "text", "thread_id", "parent_id", "repost_of", "links", "likes", "client", "language", "synthetic"]`
  - `PROFILE_COLUMNS = ["username", "created_at", "display_name", "bio", "followers", "following", "post_count", "default_avatar", "verified", "location", "ip_hash", "user_agent_hash", "email_domain", "label"]`
  - `class InputError(ValueError)`: the input cannot be analysed; the message says what to fix.
  - `connect() -> duckdb.DuckDBPyConnection`: a connection with `TimeZone` set to `UTC`, backed by a temporary database file so that data larger than memory works.
  - `load(con, comments_path: str, profiles_path: str | None = None) -> list[str]`: creates the tables below and returns warnings.
  - Table `comments`: exactly `COMMENT_COLUMNS`, in that order. `timestamp` is `TIMESTAMP` (UTC), `synthetic` is `BOOLEAN`, the rest `VARCHAR`. Empty cells are `NULL`. `username` is trimmed and never `NULL`. `comment_id` is the row number as text where the column or the cell is missing.
  - Table `profiles`: exactly `PROFILE_COLUMNS`. `created_at` is `TIMESTAMP`, the rest `VARCHAR`. One row per username (the first is kept). Empty when there is no profile file.
  - Test helper in `conftest.py`: `make_csv(tmp_path, name: str, rows: list[dict], delimiter=",") -> str` writes the rows with `csv.DictWriter` (header = keys in first-seen order, missing keys empty) and returns the path.

- [ ] **Step 1: Add dependencies**

`requirements.txt` gains the line `duckdb>=2,<3`. `requirements-dev.txt` holds `-r requirements.txt`, `pytest`, `httpx`. Run `.venv/bin/pip install -r requirements-dev.txt`.

- [ ] **Step 2: Write the failing tests** in `backend/test_load.py`

```python
import pytest
from swarm.load import COMMENT_COLUMNS, PROFILE_COLUMNS, InputError, connect, load


def rows(con, sql):
    return con.execute(sql).fetchall()


def test_minimal_file_gets_every_standard_column(tmp_path, make_csv):
    con = connect()
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "text": "hello"}, {"username": "bob", "text": ""}]))
    assert [r[0] for r in rows(con, "describe comments")] == COMMENT_COLUMNS
    assert [r[0] for r in rows(con, "describe profiles")] == PROFILE_COLUMNS
    assert rows(con, "select comment_id, username, text, timestamp from comments order by 1") == [("1", "ann", "hello", None), ("2", "bob", None, None)]
    assert rows(con, "select count(*) from profiles") == [(0,)]
    assert any("timestamp" in w for w in warnings)


def test_header_case_spaces_and_unknown_columns(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text(" Username ,TEXT,shoe_size\nann,hi,42\n", encoding="utf-8")
    con = connect()
    warnings = load(con, str(path))
    assert rows(con, "select username, text from comments") == [("ann", "hi")]
    assert any("shoe_size" in w for w in warnings)


def test_semicolons_and_byte_order_mark(tmp_path):
    path = tmp_path / "c.csv"
    path.write_bytes(b"\xef\xbb\xbfusername;text\nann;\"one; two\"\n")
    con = connect()
    load(con, str(path))
    assert rows(con, "select username, text from comments") == [("ann", "one; two")]


def test_quoted_text_with_line_breaks_commas_and_quotes_is_one_row(tmp_path, make_csv):
    con = connect()
    text = 'first line\nsecond, with "quotes"'
    load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "text": text}]))
    assert rows(con, "select text from comments") == [(text,)]


def test_path_with_space_and_quote(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "it's a file.csv", [{"username": "ann", "text": "hi"}]))
    assert rows(con, "select count(*) from comments") == [(1,)]


def test_usernames_are_trimmed_and_rows_without_one_are_dropped(tmp_path, make_csv):
    con = connect()
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": " ann ", "text": "a"}, {"username": "", "text": "b"}]))
    assert rows(con, "select username from comments") == [("ann",)]
    assert any("1" in w and "username" in w for w in warnings)


def test_timestamps_are_utc_and_bad_ones_become_null(tmp_path, make_csv):
    con = connect()
    stamps = ["2026-11-01T10:00:00", "2026-11-01T12:00:00+02:00", "2026-11-01T10:00:00Z", "not a date"]
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": "ann", "timestamp": s} for s in stamps]))
    got = rows(con, "select strftime(timestamp, '%Y-%m-%dT%H:%M:%SZ') from comments order by comment_id::int")
    assert got == [("2026-11-01T10:00:00Z",)] * 3 + [(None,)]
    assert any("1" in w and "timestamp" in w for w in warnings)


def test_synthetic_flag(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": "a", "synthetic": "1"}, {"username": "b", "synthetic": "true"}, {"username": "c", "synthetic": ""}]))
    assert rows(con, "select synthetic from comments order by username") == [(True,), (True,), (False,)]


def test_profiles_keep_first_row_per_username(tmp_path, make_csv):
    con = connect()
    comments = make_csv(tmp_path, "c.csv", [{"username": "ann", "text": "hi"}])
    profiles = make_csv(tmp_path, "p.csv", [{"username": "ann", "label": "human", "created_at": "2020-01-01"},
                                            {"username": "ann", "label": "bot"}])
    warnings = load(con, comments, profiles)
    assert rows(con, "select username, label, strftime(created_at, '%Y-%m-%d') from profiles") == [("ann", "human", "2020-01-01")]
    assert any("ann" in w or "duplicate" in w.lower() for w in warnings)


def test_profile_file_without_username_is_ignored_with_a_warning(tmp_path, make_csv):
    con = connect()
    warnings = load(con, make_csv(tmp_path, "c.csv", [{"username": "ann"}]), make_csv(tmp_path, "p.csv", [{"label": "bot"}]))
    assert rows(con, "select count(*) from profiles") == [(0,)]
    assert any("username" in w for w in warnings)


@pytest.mark.parametrize("content", ["", "username,text\n", "text\nhello\n"])
def test_unusable_comment_files_raise_input_error(tmp_path, content):
    path = tmp_path / "c.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(InputError):
        load(connect(), str(path))


def test_missing_file_raises_input_error(tmp_path):
    with pytest.raises(InputError):
        load(connect(), str(tmp_path / "nope.csv"))
```

`make_csv` is a pytest fixture in `conftest.py` that returns the helper function.

- [ ] **Step 3: Run** `.venv/bin/python -m pytest test_load.py -q`. Expected: every test fails with an import error.

- [ ] **Step 4: Implement `load.py`**

Read each file with `read_csv(?, header=true, all_varchar=true)`; DuckDB detects the delimiter and strips the byte-order mark. Find the present columns with `describe`, match them to the standard names in lower case, and build each table with a `select` that takes the column when present and `NULL` otherwise. Time columns: `try_cast(x as timestamptz)::timestamp`. `synthetic`: true for `1` and `true` in any case. Wrap DuckDB's `IOException` and an empty or header-only file in `InputError`.

One warning each for: every standard column that is missing (one line naming them all per file), unknown columns, dropped rows without a username (with the count), unreadable timestamps (with the count), duplicate profile usernames (with the count), a profile file without `username`.

- [ ] **Step 5: Run** `.venv/bin/python -m pytest test_load.py -q`. Expected: all pass.

- [ ] **Step 6: Commit** `load.py`, `conftest.py`, `test_load.py`, `requirements.txt`, `requirements-dev.txt` with message `core: load the standard CSV format`.

---

### Task 2: Synthetic data in the standard format

**Files:**
- Rewrite: `backend/swarm/synthetic.py`
- Create: `backend/test_synthetic.py`
- Delete: `backend/test_detect.py` (it tests the old skeleton; task 3 writes the new one)

**Interfaces:**
- Produces:
  - `generate(seed: int = 0) -> tuple[list[dict], list[dict]]`: comment rows and profile rows, keys from the standard columns.
  - `write(directory: str, seed: int = 0) -> tuple[str, str]`: writes `comments.csv` and `profiles.csv` there and returns both paths.
  - `python -m swarm.synthetic DIRECTORY` calls `write` and prints the two paths.

The population, which later tasks' expected numbers depend on. Timestamps fall in one day starting 2026-11-01T00:00:00Z. Sentences are 6 to 14 random words from the existing `WORDS` list.

| Accounts | Label | Comments |
|---|---|---|
| `user_000` … `user_199` | `human` | 20 random sentences each |
| 60 of the users | | the breaking-news text `Breaking: bridge closed after storm https://news.example/bridge`, once each, within 120 s |
| 80 of the users | | one repost each of `viral1` (`repost_of`), empty text, within 600 s |
| 50 of the users | | `good morning`, once each |
| `fan_00` … `fan_39` | `human` | 30 random sentences each, plus reposts of 4 different posts drawn from `celeb0` … `celeb29` |
| `newsfeed_0` … `newsfeed_2` | `benign_feed` | the same 5 headlines `WIRE: <sentence>`, each within 20 s |
| `troll_0_0` … `troll_0_7` | `bot:swarm_0` | 6 campaign messages `@<random user> <sentence>`, every member posts each within 30 s; plus 10 random sentences each |
| `troll_1_0` … `troll_1_4` | `bot:swarm_1` | the same pattern with its own 6 messages |

Every comment has `comment_id` (`syn0`, `syn1`, …), `username`, `timestamp` (ISO 8601 with `Z`), `text`, `repost_of`, `synthetic = 1`. Rows are shuffled. Profiles: one row per account with `username`, `label`, `created_at`. Users, fans and feeds get creation dates spread evenly over 2023-01-01 to 2025-12-31; each swarm's accounts are created within 10 days of each other.

- [ ] **Step 1: Write the failing tests** in `backend/test_synthetic.py`

```python
import csv
from collections import Counter
from swarm.synthetic import generate, write


def test_population():
    comments, profiles = generate()
    assert len(comments) == 5773
    assert all(c["synthetic"] == 1 for c in comments)
    assert Counter(p["label"] for p in profiles) == {"human": 240, "benign_feed": 3, "bot:swarm_0": 8, "bot:swarm_1": 5}
    assert {c["username"] for c in comments} == {p["username"] for p in profiles}


def test_same_seed_same_data():
    assert generate(3) == generate(3)
    assert generate(3) != generate(4)


def test_write_makes_two_readable_files(tmp_path):
    comments_path, profiles_path = write(str(tmp_path))
    with open(comments_path, newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 5773
    with open(profiles_path, newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 256
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest test_synthetic.py -q`. Expected: fail (old `generate` returns a list).
- [ ] **Step 3: Rewrite `synthetic.py`** to the table above. Keep the module docstring's warning that numbers on this data show that the code works, not how good detection is.
- [ ] **Step 4: Run** the same command. Expected: 3 passed.
- [ ] **Step 5: Commit** `synthetic.py`, `test_synthetic.py` and the deletion of `test_detect.py` with message `core: synthetic data in the standard format`.

---

### Task 3: Detection

**Files:**
- Rewrite: `backend/swarm/detect.py`
- Create: `backend/test_detect.py`

**Interfaces:**
- Consumes: tables `comments`, `profiles` and `InputError`, `connect`, `load` from task 1; `write` from task 2; `make_csv` from `conftest.py`.
- Produces:
  - Constants `MIN_WORDS = 5`, `MIN_SHARED = 2`, `ALPHA = 0.01`, `MIN_SIZE = 3`, `PAIR_BUDGET = 1_000_000_000`, `KINDS = ("text", "link", "repost", "reply")`, at the top of the file with one comment each: the data owner tunes them.
  - `detect(con, *, min_shared=MIN_SHARED, alpha=ALPHA, min_size=MIN_SIZE, pair_budget=PAIR_BUDGET) -> tuple[dict, list[str]]`. Returns `(signals, warnings)`. `signals` maps every kind to `{"status": "used" | "skipped", "reason": str | None, "items": int, "links": int}`. Raises `InputError` naming `text`, `links`, `repost_of`, `parent_id` when no kind produced an item.
  - Table `item(username, kind, key UBIGINT, value VARCHAR, first_seen TIMESTAMP, last_seen TIMESTAMP)`: one row per account and item. `value` is what a person would recognise: the original text of the earliest such comment, the URL, or the id.
  - Table `link(u1, u2, kind, shared BIGINT)`: the links, `u1 < u2`.
  - Table `member(username, cluster VARCHAR, copied_share DOUBLE)` and table `cluster(cluster VARCHAR, size BIGINT, confidence DOUBLE)`: **every** group of at least `min_size` accounts, whatever its confidence. The cut at `MIN_CONFIDENCE` is applied by callers.
  - `cluster` id: `hashlib.sha1(",".join(sorted(usernames)).encode()).hexdigest()[:10]`.

**The algorithm.** These queries were measured on 6.6 million comments (design, "What the data showed"); keep their logic.

Items. A repost contributes only its `repost` item:

```sql
with c as (select comment_id, username, timestamp as ts, text, links, parent_id, repost_of from comments),
t as (select *, regexp_extract_all(
        regexp_replace(regexp_replace(lower(coalesce(text, '')), 'https?://\S+', ' ', 'g'), '@[\p{L}\p{N}_]+', ' ', 'g'),
        '[\p{L}\p{N}_]+') as words
      from c where repost_of is null),
raw as (
  select username, 'repost' as kind, hash(repost_of) as key, repost_of as value, ts from c where repost_of is not null
  union all
  select username, 'text', hash(array_to_string(words, ' ')), text, ts from t where len(words) >= 5   -- MIN_WORDS
  union all
  select username, 'link', hash(url), url, ts
    from (select username, ts, rtrim(unnest(regexp_extract_all(coalesce(text, '') || ' ' || coalesce(links, ''), 'https?://\S+')), '.,)') as url
          from c where repost_of is null)
  union all
  select username, 'reply', hash(parent_id), parent_id, ts from c where parent_id is not null and repost_of is null)
select username, kind, key, arg_min(value, ts) as value, min(ts) as first_seen, max(ts) as last_seen
from raw group by username, kind, key
```

`arg_min(value, ts)` returns `NULL` when every `ts` is `NULL`; fall back to `any_value(value)`.

Counts: `df(kind, key, df)` = accounts per item; `n(username, kind, n)` = items per account per kind; per kind `S = sum(df * df) / (sum(df) * sum(df))` as doubles.

Budget: the pair rows an item costs is `df * (df - 1) / 2`. Add items up from the smallest `df`; `max_sharers` is the largest `df` whose running total stays within `pair_budget`. Items with a larger `df` take no part in pairing; add one warning with how many items were left out and the `max_sharers` used. They still count in `n` and `S`.

Pairs: self-join `item` on `(kind, key)` with `a.username < b.username` for items with `2 <= df <= max_sharers`; `c` = number of rows per `(kind, u1, u2)`.

Chance test, per pair row:

```sql
expected = n1 * n2 * S                                  -- n1, n2: the two accounts' item counts in this kind
logp = case when expected < c
            then c * ln(expected) - expected - lgamma(c + 1) - ln(1 - expected / (c + 1))
            else 0 end                                   -- log of an upper bound on P(Poisson(expected) >= c)
```

Benjamini-Hochberg over all pair rows of all kinds together, `m` = their number:

```sql
select max(logp) from (select logp, row_number() over (order by logp) as k from pairs where logp < 0)
where logp <= ln(alpha) + ln(k) - ln(m)                  -- NULL: nothing is significant
```

A pair row is a link when `c >= min_shared` and `logp <=` that cut.

Clusters: union-find in Python over the links of all kinds; groups of at least `min_size` accounts. `# shortcut: union-find in memory, fine to about 50 million links; move to an in-database method beyond that`.

Copied share of a member: of its rows in `item` (all kinds), the share whose `(kind, key)` at least one other member of the same cluster also has. `confidence` = the average copied share over the members.

- [ ] **Step 1: Write the failing tests** in `backend/test_detect.py`

```python
import pytest
from swarm.detect import detect
from swarm.load import InputError, connect, load
from swarm.synthetic import generate, write

WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima".split()


def unique(owner, n):
    """n texts nobody else has."""
    return [{"username": owner, "text": f"{owner} wrote note number {i} about {WORDS[i % 12]} today"} for i in range(n)]


def shared(owners, n, tag="plan"):
    return [{"username": o, "text": f"the {tag} for item {i} is ready for everyone now"} for i in range(n) for o in owners]


def background(n_accounts, n_texts):
    return [row for a in range(n_accounts) for row in unique(f"bg{a}", n_texts)]


def run(tmp_path, make_csv, rows, **kwargs):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", rows))
    signals, warnings = detect(con, **kwargs)
    return con, signals, warnings


def clusters(con):
    members = con.execute("select cluster, username from member order by 1, 2").fetchall()
    out = {}
    for cluster, username in members:
        out.setdefault(cluster, set()).add(username)
    return list(out.values())


def test_synthetic_swarms_are_found_and_ordinary_users_are_in_no_cluster(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    detect(con)
    found = clusters(con)
    assert {f"troll_0_{i}" for i in range(8)} in found
    assert {f"troll_1_{i}" for i in range(5)} in found
    # breaking news, a viral repost, a greeting and a fan community link nobody
    assert not any(name.startswith(("user_", "fan_")) for group in found for name in group)
    confidence = dict(con.execute("select size, round(confidence, 3) from cluster").fetchall())
    assert confidence[8] == 0.375 and confidence[5] == 0.375      # 6 of 16 items are shared


def test_benign_feeds_are_flagged_known_limit(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    detect(con)
    assert {"newsfeed_0", "newsfeed_1", "newsfeed_2"} in clusters(con)


def test_one_shared_item_links_nobody(tmp_path, make_csv):
    rows = shared(["a", "b", "c"], 1) + unique("a", 5) + unique("b", 5) + unique("c", 5) + background(50, 20)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == []


def test_everyone_sharing_everything_is_not_surprising(tmp_path, make_csv):
    rows = [{"username": f"u{a}", "text": f"see https://x.example/{k}"} for a in range(10) for k in range(3)]
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == []


def test_loose_group_is_a_cluster_with_low_confidence(tmp_path, make_csv):
    trio = ["a", "b", "c"]
    rows = shared(trio, 6) + [r for o in trio for r in unique(o, 40)] + background(50, 40)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [set(trio)]
    assert con.execute("select round(confidence, 3) from cluster").fetchall() == [(0.13,)]   # 6 of 46


def test_copies_differ_by_case_mentions_and_links_in_any_script(tmp_path, make_csv):
    variants = ["Привет всем это важная новость номер {i}", "@bob ПРИВЕТ всем это важная новость номер {i} https://x.example/a",
                "привет ВСЕМ, это важная новость номер {i}!"]
    rows = [{"username": o, "text": v.format(i=i)} for i in range(6) for o, v in zip("abc", variants)]
    rows += [r for o in "abc" for r in unique(o, 10)] + background(50, 20)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert clusters(con) == [{"a", "b", "c"}]


def test_a_repost_gives_only_its_repost_item(tmp_path, make_csv):
    rows = [{"username": "a", "text": "RT this is the original text of the post https://x.example/1", "repost_of": "p1", "parent_id": "q1"}]
    con, _, _ = run(tmp_path, make_csv, rows)
    assert con.execute("select kind, value from item").fetchall() == [("repost", "p1")]


def test_an_account_repeating_itself_is_one_item_and_no_link(tmp_path, make_csv):
    rows = [{"username": o, "text": f"{o} says the very same thing again and again"} for o in "abc" for _ in range(50)]
    con, signals, _ = run(tmp_path, make_csv, rows + background(20, 5))
    assert con.execute("select count(*) from item where username in ('a', 'b', 'c')").fetchall() == [(3,)]
    assert clusters(con) == []


def test_text_without_words_gives_no_item(tmp_path, make_csv):
    rows = [{"username": "a", "text": t} for t in ["😀😀😀😀😀😀", "!!! ... ???", "   ", "too short"]] + unique("b", 3)
    con, _, _ = run(tmp_path, make_csv, rows)
    assert con.execute("select count(*) from item where username = 'a'").fetchall() == [(0,)]


def test_missing_columns_skip_their_signals(tmp_path, make_csv):
    comments, _ = generate()
    rows = [{"username": c["username"], "text": c["text"]} for c in comments]
    con, signals, _ = run(tmp_path, make_csv, rows)
    assert signals["text"]["status"] == "used" and signals["text"]["links"] > 0
    assert signals["repost"] == {"status": "skipped", "reason": signals["repost"]["reason"], "items": 0, "links": 0}
    assert "repost_of" in signals["repost"]["reason"]
    assert {f"troll_0_{i}" for i in range(8)} in clusters(con)


def test_no_content_column_at_all_is_an_input_error(tmp_path, make_csv):
    con = connect()
    load(con, make_csv(tmp_path, "c.csv", [{"username": "a", "timestamp": "2026-11-01T10:00:00Z"}]))
    with pytest.raises(InputError, match="text.*links.*repost_of.*parent_id"):
        detect(con)


def test_a_tiny_pair_budget_warns_instead_of_failing(tmp_path):
    con = connect()
    load(con, *write(str(tmp_path)))
    signals, warnings = detect(con, pair_budget=10)
    assert any("budget" in w.lower() for w in warnings)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest test_detect.py -q`. Expected: fail on import of the new `detect` signature.
- [ ] **Step 3: Rewrite `detect.py`** as specified above. A kind is `skipped` with a reason naming its column(s) when the column is entirely `NULL` in `comments` (`text` needs `text`; `link` needs `text` or `links`; `repost` needs `repost_of`; `reply` needs `parent_id`). `signals[kind]["items"]` is the number of rows in `item` of that kind, `["links"]` the number of rows in `link`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest test_detect.py -q`. Expected: all pass. If `test_loose_group…` or the synthetic test fails on a number, check the formulas against this plan before touching the test.
- [ ] **Step 5: Commit** `detect.py`, `test_detect.py` with message `core: link accounts that share content beyond chance`.

---

### Task 4: Metrics and the result document

**Files:**
- Create: `backend/swarm/evaluate.py`, `backend/swarm/core.py`, `backend/test_evaluate.py`, `backend/test_core.py`

**Interfaces:**
- Consumes: everything task 3 produces.
- Produces:
  - `evaluate.THRESHOLDS = (0, 0.05, 0.1, 0.2, 0.3, 0.5)`
  - `evaluate.evaluate(con, min_confidence: float) -> dict | None`. `None` when no profile has a label. Otherwise:
    ```python
    {"labelled_accounts": int,            # labelled accounts with at least one row in item
     "labelled_without_content": int,     # labelled accounts with none; they are not counted below
     "at_min_confidence": counts,
     "by_threshold": [counts, ...],       # one per THRESHOLDS, in order
     "by_label": {label: {"accounts": int, "flagged": int}}}   # at min_confidence
    # counts = {"min_confidence", "true_positives", "false_positives", "false_negatives",
    #           "true_negatives", "precision", "recall", "false_positive_rate"}
    ```
    An account is a bot when its label is `bot` or starts with `bot:`. It is flagged at a threshold when it is in a cluster with `confidence >=` that threshold. Ratios are rounded to 4 decimals and `None` when the denominator is 0.
  - `core.MIN_CONFIDENCE = 0.2`, `core.MAX_EDGES = 500`, `core.MAX_ITEMS = 20`
  - `core.analyze(comments_path, profiles_path=None, *, min_confidence=MIN_CONFIDENCE, min_shared=MIN_SHARED, alpha=ALPHA, min_size=MIN_SIZE, pair_budget=PAIR_BUDGET) -> dict`: the document in the spec's "Output" section, JSON-serialisable. It opens its own connection with `load.connect()` and closes it.

Result details the spec leaves implicit:
- `source.comments_file` and `profiles_file` are base names, not full paths. `source.synthetic` is true when any comment has `synthetic`.
- `warnings` = load warnings, then detect warnings.
- `clusters` holds only clusters with `confidence >= min_confidence`, sorted by confidence descending, then size descending, then id. `confidence` and `copied_share` are rounded to 3 decimals.
- `accounts` is sorted by `copied_share` descending, then username.
- `edges`: rows of `link` inside the cluster, strongest `shared` first, at most `MAX_EDGES`. `edge_count` is the number before the cut.
- `top_items`: the cluster's items that at least 2 members have, most members first, at most `MAX_ITEMS`; each with `kind`, `value`, `accounts`, `first_seen`, `last_seen` (over the members' rows).
- `first_seen`, `last_seen` of the cluster: over those shared items. Times are text like `2026-11-01T03:13:55Z`, or `null`.
- `created_within_30_days`: among members with a `created_at`, the largest number created within one 30-day window, as `{"accounts": k, "of": members_with_a_date}`; `null` when no member has a date.

- [ ] **Step 1: Write the failing tests**

`backend/test_evaluate.py`:

```python
from swarm.detect import detect
from swarm.evaluate import THRESHOLDS, evaluate
from swarm.load import connect, load
from swarm.synthetic import write


def analysed(tmp_path, with_profiles=True):
    con = connect()
    comments, profiles = write(str(tmp_path))
    load(con, comments, profiles if with_profiles else None)
    detect(con)
    return con


def test_metrics_on_synthetic_data(tmp_path):
    m = evaluate(analysed(tmp_path), 0.2)
    assert m["labelled_accounts"] == 256 and m["labelled_without_content"] == 0
    assert m["at_min_confidence"] == {
        "min_confidence": 0.2, "true_positives": 13, "false_positives": 3, "false_negatives": 0,
        "true_negatives": 240, "precision": 0.8125, "recall": 1.0, "false_positive_rate": 0.0123}
    assert [c["min_confidence"] for c in m["by_threshold"]] == list(THRESHOLDS)
    assert m["by_label"]["benign_feed"] == {"accounts": 3, "flagged": 3}     # the known limit, visible
    assert m["by_label"]["human"] == {"accounts": 240, "flagged": 0}
    assert m["by_label"]["bot:swarm_1"] == {"accounts": 5, "flagged": 5}


def test_a_higher_cut_flags_fewer(tmp_path):
    m = evaluate(analysed(tmp_path), 0.5)        # the swarms sit at 0.375, the feeds at 1.0
    assert m["at_min_confidence"]["true_positives"] == 0
    assert m["at_min_confidence"]["false_positives"] == 3
    assert m["at_min_confidence"]["precision"] == 0.0


def test_no_labels_no_metrics(tmp_path):
    assert evaluate(analysed(tmp_path, with_profiles=False), 0.2) is None
```

`backend/test_core.py`:

```python
import json
from swarm.core import analyze
from swarm.synthetic import write


def test_result_document(tmp_path):
    result = analyze(*write(str(tmp_path)))
    json.dumps(result)
    assert result["source"] == {"comments_file": "comments.csv", "profiles_file": "profiles.csv",
                                "comments": 5773, "accounts": 256, "synthetic": True}
    assert result["parameters"] == {"min_words": 5, "min_shared": 2, "alpha": 0.01, "min_size": 3, "min_confidence": 0.2}
    assert [c["size"] for c in result["clusters"]] == [3, 8, 5]            # feeds at 1.0, then the swarms
    assert result["metrics"]["at_min_confidence"]["precision"] == 0.8125
    swarm = result["clusters"][1]
    assert set(swarm) == {"id", "size", "confidence", "accounts", "edge_count", "edges", "top_items",
                          "first_seen", "last_seen", "created_within_30_days"}
    assert swarm["confidence"] == 0.375 and swarm["edge_count"] == 28 and len(swarm["edges"]) == 28
    assert swarm["accounts"][0] == {"username": "troll_0_0", "copied_share": 0.375}
    assert swarm["edges"][0].keys() == {"source", "target", "kind", "shared"}
    assert len(swarm["top_items"]) == 6 and swarm["top_items"][0]["accounts"] == 8
    assert swarm["top_items"][0]["kind"] == "text" and swarm["top_items"][0]["first_seen"].endswith("Z")
    assert swarm["created_within_30_days"] == {"accounts": 8, "of": 8}


def test_without_profiles(tmp_path):
    comments, _ = write(str(tmp_path))
    result = analyze(comments)
    assert result["metrics"] is None and result["source"]["profiles_file"] is None
    assert result["clusters"][0]["created_within_30_days"] is None


def test_min_confidence_cuts_the_list(tmp_path):
    result = analyze(*write(str(tmp_path)), min_confidence=0.5)
    assert [c["size"] for c in result["clusters"]] == [3]
    assert result["parameters"]["min_confidence"] == 0.5
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest test_evaluate.py test_core.py -q`. Expected: import errors.
- [ ] **Step 3: Implement `evaluate.py`, then `core.py`.**
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: all tests of tasks 1–4 pass.
- [ ] **Step 5: Commit** the four files with message `core: metrics and the result document`.

---

### Task 5: Command line

**Files:**
- Create: `backend/swarm/__main__.py`, `backend/test_cli.py`

**Interfaces:**
- Consumes: `core.analyze`, `load.InputError`.
- Produces: `python -m swarm COMMENTS [--profiles FILE] [--out FILE] [--min-confidence X]`.
  - Warnings go to standard error, one per line, prefixed `warning: `.
  - Standard output: one line per signal (status, items, links), the number of clusters, one line per cluster (id, size, confidence), and, with labels, precision, recall and false-positive rate at the cut. If `source.synthetic` is true, the first line says the data is synthetic.
  - `--out` writes the result as JSON (UTF-8, `ensure_ascii=False`, indent 1). Without it only the summary is printed.
  - `InputError`: print `error: <message>` to standard error and exit with code 2. No traceback.

- [ ] **Step 1: Write the failing tests** in `backend/test_cli.py`

```python
import json
import subprocess
import sys
from swarm.synthetic import write


def cli(*args):
    return subprocess.run([sys.executable, "-m", "swarm", *args], capture_output=True, text=True)


def test_run_writes_the_result_and_prints_a_summary(tmp_path):
    comments, profiles = write(str(tmp_path))
    out = tmp_path / "result.json"
    done = cli(comments, "--profiles", profiles, "--out", str(out))
    assert done.returncode == 0, done.stderr
    assert len(json.loads(out.read_text(encoding="utf-8"))["clusters"]) == 3
    assert "synthetic" in done.stdout.lower() and "3 clusters" in done.stdout and "0.8125" in done.stdout


def test_warnings_go_to_standard_error(tmp_path, make_csv):
    path = make_csv(tmp_path, "c.csv", [{"username": f"u{i}", "text": f"a text of five words number {i}"} for i in range(5)])
    done = cli(path)
    assert done.returncode == 0 and "warning: " in done.stderr and "timestamp" in done.stderr


def test_bad_input_is_one_line_and_exit_code_2(tmp_path, make_csv):
    done = cli(make_csv(tmp_path, "c.csv", [{"text": "no username column here at all"}]))
    assert done.returncode == 2 and done.stderr.startswith("error: ") and "username" in done.stderr
    assert "Traceback" not in done.stderr
    assert cli(str(tmp_path / "nope.csv")).returncode == 2
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest test_cli.py -q`. Expected: fail, `No module named swarm.__main__`.
- [ ] **Step 3: Implement `__main__.py`** with `argparse`.
- [ ] **Step 4: Run** the same command. Expected: 3 passed.
- [ ] **Step 5: Commit** both files with message `core: command line`.

---

### Task 6: Cresci 2017 converter and the first real numbers

**Files:**
- Create: `backend/swarm/cresci.py`, `backend/test_cresci.py`
- Modify: `PLAN.md` (one row in "Results")

**Interfaces:**
- Produces: `convert(source_dir: str, out_dir: str) -> None` and `python -m swarm.cresci SOURCE_DIR OUT_DIR`. Writes `comments.csv` and `profiles.csv` in the standard format.

Source layout: `SOURCE_DIR/<set>.csv.zip` holding `<set>.csv/users.csv` and `<set>.csv/tweets.csv`. Sets and labels: `genuine_accounts` → `human`; `social_spambots_1`, `_2`, `_3` → `bot:social_1`, `bot:social_2`, `bot:social_3`; `traditional_spambots_1` → `bot:traditional_1`; `fake_followers` → `bot:fake_followers`. A set whose zip is absent is skipped with a printed line. The other `traditional_spambots` sets have no tweets and are not converted.

Mapping. `NULL`, `\N`, `0` and empty mean "no value" for the id columns.

| Standard column | Source |
|---|---|
| `comment_id` | tweets `id` |
| `username` | tweets `user_id`; users `id`. **The numeric id, never `name` or `screen_name`.** |
| `timestamp` | tweets `timestamp` (`2010-08-31 21:24:14`) as `2010-08-31T21:24:14Z`. Rows without a readable one are dropped. |
| `text` | tweets `text`, NUL characters removed |
| `parent_id` | tweets `in_reply_to_status_id` |
| `repost_of` | tweets `retweeted_status_id` |
| `likes` | tweets `favorite_count` |
| `client` | tweets `source` with HTML tags removed |
| `created_at` | users `timestamp`, same conversion; where that column is absent (`fake_followers`), users `created_at` in the form `Thu Apr 06 15:24:15 +0000 2007` |
| `followers`, `following`, `post_count` | users `followers_count`, `friends_count`, `statuses_count` |
| `default_avatar`, `verified` | users `default_profile_image`, `verified`: `1` or `0` |

Names, bios, locations and URLs are left out on purpose: they are personal data and the core does not use them. Read the zips with `zipfile` and `csv.DictReader` (`encoding="utf-8", errors="replace", newline=""`, `csv.field_size_limit(10**9)`), streaming row by row.

- [ ] **Step 1: Write the failing test** in `backend/test_cresci.py`. It builds its own tiny zips; it never touches the real dataset.

```python
import csv
import zipfile
from swarm.cresci import convert


def make_set(folder, name, users, tweets):
    def text(rows):
        return "\n".join(",".join(f'"{v}"' for v in row) for row in rows) + "\n"
    with zipfile.ZipFile(folder / f"{name}.csv.zip", "w") as z:
        z.writestr(f"{name}.csv/users.csv", text(users))
        z.writestr(f"{name}.csv/tweets.csv", text(tweets))


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_convert(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir(); out.mkdir()
    users = [["id", "name", "screen_name", "followers_count", "friends_count", "statuses_count", "default_profile_image", "verified", "timestamp"],
             ["11", "Real Name", "realhandle", "5", "7", "2", "NULL", "NULL", "2012-01-05 08:00:00"]]
    tweets = [["id", "text", "source", "user_id", "in_reply_to_status_id", "retweeted_status_id", "favorite_count", "timestamp"],
              ["900", "hello world", '<a href=x rel=nofollow>web</a>', "11", "0", "0", "3", "2014-03-01 10:00:00"],
              ["901", "RT something", "web", "11", "NULL", "555", "0", "2014-03-01 10:05:00"],
              ["902", "no time", "web", "11", "0", "0", "0", ""]]
    make_set(src, "genuine_accounts", users, tweets)
    make_set(src, "social_spambots_1", [users[0], ["22", "Bot", "bothandle", "0", "0", "1", "1", "NULL", "2012-01-06 08:00:00"]],
             [tweets[0], ["903", "buy now", "web", "22", "900", "0", "0", "2014-03-02 10:00:00"]])
    convert(str(src), str(out))

    comments, profiles = read(out / "comments.csv"), read(out / "profiles.csv")
    assert [(c["comment_id"], c["username"], c["timestamp"], c["parent_id"], c["repost_of"], c["client"]) for c in comments] == [
        ("900", "11", "2014-03-01T10:00:00Z", "", "", "web"),
        ("901", "11", "2014-03-01T10:05:00Z", "", "555", "web"),
        ("903", "22", "2014-03-02T10:00:00Z", "900", "", "web")]
    assert [(p["username"], p["label"], p["created_at"], p["default_avatar"]) for p in profiles] == [
        ("11", "human", "2012-01-05T08:00:00Z", "0"), ("22", "bot:social_1", "2012-01-06T08:00:00Z", "1")]
    everything = (out / "comments.csv").read_text() + (out / "profiles.csv").read_text()
    assert "Real Name" not in everything and "realhandle" not in everything and "bothandle" not in everything
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest test_cresci.py -q`. Expected: import error.
- [ ] **Step 3: Implement `cresci.py`.**
- [ ] **Step 4: Run** the same command. Expected: 1 passed.
- [ ] **Step 5: Run on the real data** (only where `backend/data/cresci-2017.csv/` exists; otherwise report this step as skipped):

```bash
.venv/bin/python -m swarm.cresci data/cresci-2017.csv/datasets_full.csv data/cresci-std
.venv/bin/python -m swarm data/cresci-std/comments.csv --profiles data/cresci-std/profiles.csv --out data/cresci-result.json
```

Expected, from the design's measurements: about 6.64 million comments; at the default cut precision at least 0.99 and at most 1% of humans flagged; share flagged at least 0.90 for `bot:social_1`, `bot:social_2`, `bot:social_3`, and between 0.3 and 0.6 for `bot:traditional_1` and `bot:fake_followers`; a run time of a few minutes at most. Numbers far outside these mean a bug: stop and investigate before recording anything.

- [ ] **Step 6: Record the run** as a new row in the "Results" table of `PLAN.md`: date and time, dataset, variant `core, rules only`, precision, recall and false-positive rate at 0.2, and in "Change" the per-family shares plus the sentence "The cut 0.2 was chosen with these labels visible." Aggregate numbers only.
- [ ] **Step 7: Commit** `cresci.py`, `test_cresci.py`, `PLAN.md` with message `core: Cresci 2017 converter and first measured results`. Check with `git status` that nothing under `backend/data/` is staged.

---

### Task 7: HTTP API, contract and project docs

**Files:**
- Rewrite: `backend/swarm/api.py`, `docs/api.md`
- Create: `backend/test_api.py`
- Modify: `CLAUDE.md` (sections "Commands" and "Architecture"), `PLAN.md` (the "Backend" status block)

**Interfaces:**
- Consumes: `core.analyze`, `synthetic.write`.
- Produces: the FastAPI app `swarm.api:app`. The result is fixed at startup, from the first of:
  1. `RESULT_FILE`: a JSON file written by the command line;
  2. `COMMENTS_FILE` (and optionally `PROFILES_FILE`): analysed at startup;
  3. otherwise the synthetic sample, written to a temporary directory and analysed.
- Endpoints, all `GET`, CORS open for `GET` as now:
  - `/health` → `{"status": "ok"}`
  - `/api/swarms` → `{"source", "parameters", "signals", "warnings", "swarms": [...]}`; each swarm is `{"id", "size", "confidence", "edge_count", "first_seen", "last_seen", "sample"}` where `sample` is the first of `top_items` or `null`
  - `/api/swarms/{id}` → the cluster object from the result; `404` with `{"detail": "no such swarm"}` if unknown
  - `/api/metrics` → `{"source", "metrics"}`

- [ ] **Step 1: Write the failing tests** in `backend/test_api.py`

```python
import json
from fastapi.testclient import TestClient
from swarm.core import analyze
from swarm.synthetic import write


def client(monkeypatch, **env):
    for name in ("RESULT_FILE", "COMMENTS_FILE", "PROFILES_FILE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    import importlib
    import swarm.api
    return TestClient(importlib.reload(swarm.api).app)


def test_default_is_the_synthetic_sample(monkeypatch):
    c = client(monkeypatch)
    assert c.get("/health").json() == {"status": "ok"}
    body = c.get("/api/swarms").json()
    assert body["source"]["synthetic"] is True and len(body["swarms"]) == 3
    first = body["swarms"][0]
    assert set(first) == {"id", "size", "confidence", "edge_count", "first_seen", "last_seen", "sample"}
    detail = c.get(f"/api/swarms/{first['id']}").json()
    assert detail["id"] == first["id"] and detail["accounts"]
    assert c.get("/api/swarms/nope").status_code == 404
    assert c.get("/api/metrics").json()["metrics"]["at_min_confidence"]["precision"] == 0.8125


def test_serves_a_result_file(monkeypatch, tmp_path):
    result = analyze(*write(str(tmp_path)), min_confidence=0.5)
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert len(client(monkeypatch, RESULT_FILE=str(path)).get("/api/swarms").json()["swarms"]) == 1


def test_analyses_a_comments_file(monkeypatch, tmp_path):
    comments, _ = write(str(tmp_path))
    body = client(monkeypatch, COMMENTS_FILE=comments).get("/api/metrics").json()
    assert body["metrics"] is None and body["source"]["profiles_file"] is None
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest test_api.py -q`. Expected: fail (the old `api.py` imports names that no longer exist).
- [ ] **Step 3: Rewrite `api.py`.**
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: every test in `backend/` passes.
- [ ] **Step 5: Rewrite `docs/api.md`** for the front-end owner and the data owner: the endpoints above with one real example response each (take them from the running synthetic sample), the two input tables from the spec's "Input format" including "What is truly required", and the command line. State at the top that `verdict` is gone and `confidence` replaces it. Plain language; the method itself stays in `docs/core-design.md`.
- [ ] **Step 6: Update `CLAUDE.md`.** "Commands": installing with `requirements-dev.txt`, `python -m swarm.synthetic DIR`, `python -m swarm COMMENTS --profiles … --out …`, the three ways to start the API, tests, the Docker build. "Architecture": one bullet per module in the file-structure table above, and what is not built yet (part 2). Remove the description of the old skeleton.
- [ ] **Step 7: Update the "Backend" status block in `PLAN.md`**: what is done, and for Makeee22 the three environment variables and that the image still listens on port 8000 and has not been built locally (no Docker on the backend owner's machine).
- [ ] **Step 8: Check the image inputs by reading.** `backend/Dockerfile` copies `requirements.txt` and `swarm/` only; confirm that is still everything the app needs at run time and that no file under `data/` is copied.
- [ ] **Step 9: Commit** `api.py`, `test_api.py`, `docs/api.md`, `CLAUDE.md`, `PLAN.md` with message `core: API on the new result, contract and docs`.

---

### Task 8 (optional, cut first): similar-text signal

Do this only when tasks 1–7 are merged and time remains before the feature freeze.

**Files:**
- Create: `backend/swarm/similar.py`, `backend/test_similar.py`
- Modify: `backend/swarm/detect.py`, `backend/swarm/core.py`, `backend/swarm/__main__.py`, `backend/swarm/synthetic.py`, `PLAN.md`

**Interfaces:**
- Produces:
  - `similar.MODEL = "minishlab/potion-base-8M"` (English; `minishlab/potion-multilingual-128M` for other languages), `similar.THRESHOLD = 0.9`, `similar.MAX_TEXTS = 100_000`
  - `similar.add_items(con, model=MODEL, threshold=THRESHOLD, max_texts=MAX_TEXTS) -> list[str]`: adds rows of kind `similar_text` to `item` and returns warnings. Called by `detect` after the items are built and before they are counted.
  - `detect(..., similar_text: bool = False)`, `analyze(..., similar_text: bool = False)`, command-line flag `--similar-text`. `"similar_text"` appears in `signals` only when requested.
  - `synthetic.generate(seed=0, reworded=False)`: with `reworded=True` adds `troll_2_0` … `troll_2_5`, label `bot:reworded`. Each of its 6 campaign messages is posted by every member in a different wording: the same sentence with two or three words swapped for synonyms from a small table in the module and one pair of neighbouring words exchanged. No two members post identical text.

How it works: take the distinct normalised texts of the `text` items (detect must keep them; add a column or table for it). If there are more than `max_texts`, skip with a warning. Embed them with `model2vec.StaticModel.from_pretrained(model).encode(texts)`, normalise to unit length, and compare all against all in blocks of 2,000 rows with a matrix product. Texts with cosine at least `threshold` are joined by union-find into groups. Every group with at least two distinct texts becomes one item: each account that posted any text of the group gets a row of kind `similar_text` with the group's smallest text hash as key. If `model2vec` is not installed, raise `InputError` telling the user to `pip install model2vec`. `# shortcut: all-against-all comparison, fine to 100,000 distinct texts; use an approximate-neighbour index beyond that`.

- [ ] **Step 1: Write the failing tests** in `backend/test_similar.py`, starting with `pytest.importorskip("model2vec")`:
  - `test_reworded_swarm_is_missed_without_the_layer`: on `generate(reworded=True)` written to CSV, plain `detect` yields no cluster containing a `troll_2_` account.
  - `test_reworded_swarm_is_found_with_the_layer`: with `similar_text=True`, the set of the six `troll_2_` accounts is one of the clusters, and no cluster contains a `user_` or `fan_` account.
  - `test_too_many_texts_skips_with_a_warning`: `add_items(con, max_texts=10)` returns a warning and adds no rows.
- [ ] **Step 2: Run** `.venv/bin/pip install model2vec && .venv/bin/python -m pytest test_similar.py -q`. Expected: fail on import.
- [ ] **Step 3: Implement.** If the reworded swarm is not found at 0.9, do not lower the threshold to make the test pass: report the measured cosine values between the variants instead, so the team can decide.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: all pass, including every earlier test unchanged.
- [ ] **Step 5: Measure false positives on real humans.** From `data/cresci-std/`, take the comments of 300 human accounts chosen by sorted username, capped so that distinct texts stay under 100,000, and run the command line with and without `--similar-text`. Record both rows in `PLAN.md` "Results": clusters reported and humans flagged. This is the only real-data evidence for the layer; record it whatever it shows.
- [ ] **Step 6: Commit** the changed files with message `core: optional similar-text signal`.
