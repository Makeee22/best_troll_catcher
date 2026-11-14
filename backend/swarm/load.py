"""Read the two standard CSV files into the DuckDB tables `comments` and `profiles`."""
import atexit
import shutil
import tempfile
from pathlib import Path

import duckdb

COMMENT_COLUMNS = ["comment_id", "username", "timestamp", "text", "thread_id", "parent_id",
                   "repost_of", "links", "likes", "client", "language", "synthetic"]
PROFILE_COLUMNS = ["username", "created_at", "display_name", "bio", "followers", "following",
                   "post_count", "default_avatar", "verified", "location", "ip_hash",
                   "user_agent_hash", "email_domain", "label"]
TIME_COLUMNS = {"timestamp", "created_at"}
READ = "read_csv(?, header=true, all_varchar=true)"


class InputError(ValueError):
    """The input cannot be analysed; the message says what to fix."""


_WORK_DIRS = {}


def connect():
    work = tempfile.mkdtemp(prefix="swarm-")
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    con = duckdb.connect(str(Path(work, "work.duckdb")))
    con.execute("SET TimeZone='UTC'")
    _WORK_DIRS[id(con)] = work
    return con


def close(con):
    """Close the connection and delete its temporary database now, not at exit."""
    work = _WORK_DIRS.pop(id(con), None)
    con.close()
    if work:
        shutil.rmtree(work, ignore_errors=True)


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _header(con, path):
    """Map lower-case stripped column name -> name in the file (first wins), plus all names."""
    try:
        names = [r[0] for r in con.execute(f"describe select * from {READ}", [path]).fetchall()]
    except duckdb.IOException as e:
        raise InputError(f"cannot read {path}: {e}") from None
    present = {}
    for n in names:
        present.setdefault(n.strip().lower(), n)
    return present, names


def _clean(src):
    """Empty when the cell holds only whitespace (tabs and no-break spaces too); surrounding whitespace is cut."""
    return f"nullif(regexp_replace({src}, '^[\\s\\p{{Z}}]+|[\\s\\p{{Z}}]+$', '', 'g'), '')"


def _expr(col, src):
    if col == "username":
        return f"trim({src})"
    if col in TIME_COLUMNS:
        return f"try_cast({_clean(src)} as timestamptz)::timestamp"
    if col == "synthetic":
        return f"coalesce(lower(trim({src})) in ('1', 'true'), false)"
    if col == "comment_id":
        return f"coalesce({_clean(src)}, _rn::varchar)"
    return f"{_clean(src)}"


def _missing_expr(col):
    if col == "comment_id":
        return "_rn::varchar"
    if col == "synthetic":
        return "false"
    return "null::timestamp" if col in TIME_COLUMNS else "null::varchar"


def _build(con, table, path, standard, present, names, who):
    """Create `table` from the file. Returns the warnings and the (kept, dropped, bad_time) counts."""
    warnings = []
    missing = [c for c in standard if c not in present]
    if missing:
        warnings.append(f"{who}: missing columns {', '.join(missing)}; the signals that need them are skipped")
    unknown = [n for n in names if n.strip().lower() not in standard]
    if unknown:
        warnings.append(f"{who}: ignored unknown columns {', '.join(unknown)}")
    select = ", ".join(
        f"{_expr(c, _q(present[c])) if c in present else _missing_expr(c)} as {c}" for c in standard)
    user = f"trim({_q(present['username'])})"
    tcol = next(c for c in standard if c in TIME_COLUMNS)
    bad = _q(present[tcol]) if tcol in present else None
    bad_time = (f"count(*) filter (where {user} <> '' and {_clean(bad)} is not null "
                f"and try_cast({bad} as timestamptz) is null)") if bad else "0"
    total, no_user, bad_n = con.execute(
        f"select count(*), count(*) filter (where {user} is null or {user} = ''), {bad_time} "
        f"from {READ}", [path]).fetchall()[0]
    con.execute(
        f"create or replace table {table} as select {select} from "
        f"(select *, row_number() over () as _rn from {READ}) "
        f"where {user} is not null and {user} <> ''", [path])
    if no_user:
        warnings.append(f"{who}: dropped {no_user} rows without a username")
    return warnings, total - no_user, bad_n


def load(con, comments_path, profiles_path=None):
    try:
        return _load(con, comments_path, profiles_path)
    except duckdb.Error as e:
        # a row with a different number of cells than the header ends up here
        # first line only: DuckDB's CSV errors quote the offending row, which may be private
        raise InputError(f"cannot read the CSV files: {str(e).splitlines()[0][:200]}") from None


def _load(con, comments_path, profiles_path):
    warnings = []
    present, names = _header(con, comments_path)
    if "username" not in present:
        raise InputError(f"{comments_path}: no username column; the comments file needs a username column")
    w, kept, bad = _build(con, "comments", comments_path, COMMENT_COLUMNS, present, names, "comments file")
    warnings += w
    if not kept:
        raise InputError(f"{comments_path}: no comments with a username")
    if bad:
        warnings.append(f"comments file: {bad} timestamps could not be read and are left empty")

    if profiles_path is None:
        present = None
    else:
        present, names = _header(con, profiles_path)
    if present is None or "username" not in present:
        if present is not None:
            warnings.append("profiles file: no username column; the file is ignored")
        con.execute("create or replace table profiles as select "
                    + ", ".join(f"{_missing_expr(c)} as {c}" for c in PROFILE_COLUMNS) + " where false")
        return warnings

    w, kept, bad = _build(con, "profiles_all", profiles_path, PROFILE_COLUMNS, present, names, "profiles file")
    warnings += w
    if bad:
        warnings.append(f"profiles file: {bad} created_at values could not be read and are left empty")
    # first row per username wins; row order is the file order
    con.execute("create or replace table profiles as select * from profiles_all "
                "qualify row_number() over (partition by username order by rowid) = 1")
    (kept_unique,) = con.execute("select count(*) from profiles").fetchall()[0]
    if kept_unique < kept:
        warnings.append(f"profiles file: {kept - kept_unique} duplicate usernames; the first row of each is kept")
    con.execute("drop table profiles_all")
    return warnings
