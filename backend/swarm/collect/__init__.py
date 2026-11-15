"""Collector: a link to a discussion -> the raw bundle of docs/collect-interface.md -> swarm.convert -> swarm.core.

    bundle = collect(url)                  # fetch the thread, each commenter's recent history, and note what is missing
    result, bundle = run(url)              # ... then convert and analyse

Needs the network; swarm.core never imports this package. Context.dev (key CONTEXT_DEV_API_KEY) is used where
a site needs it; Bluesky and Hacker News also work without a key, through their public APIs.
"""
import re
import tempfile
from datetime import datetime, timezone

from . import bluesky, discourse, generic, hackernews, mastodon, reddit, reviews
from .contextdev import CollectError, ContextDev, ContextDevError

__all__ = ["collect", "run", "analyse", "CollectError", "ContextDev", "ContextDevError"]

MAX_HISTORY = 100     # newest posts per commenter; more costs credits for little evidence
# order matters: the specific sites first, then the federated formats any server can run, then any page with
# schema.org comment markup (generic matches every link)
SITES = [("bluesky", bluesky), ("hackernews", hackernews), ("reddit", reddit), ("reviews", reviews),
         ("mastodon", mastodon), ("discourse", discourse), ("generic", generic)]


def _normalise(url):
    url = (url or "").strip()
    if len(url) > 500 or any(c.isspace() for c in url):
        raise CollectError("That does not look like a link.")
    return url if re.match(r"^https?://", url, re.I) else "https://" + url


def collect(url, *, history=25, max_participants=None, on_progress=None, client=None):
    """The raw bundle for a link (docs/collect-interface.md). Raises CollectError with a message for the user."""
    url = _normalise(url)
    site = next(((name, mod) for name, mod in SITES if mod.matches(url)), None)
    if site is None:
        raise CollectError(f"This site is not supported yet: {re.sub(r'^https?://', '', url).split('/')[0]}")
    # by default every site's own cap: 500 where histories are free (Bluesky, Hacker News), 150 on Reddit (credits)
    history = max(1, min(int(history), MAX_HISTORY))
    max_participants = max(1, int(getattr(site[1], "MAX_PARTICIPANTS", 150) if max_participants is None else max_participants))
    client = client or ContextDev.from_env()
    before = client.credits_used
    got = site[1].collect(url, client, history, max_participants, on_progress)
    bundle = {
        "url": url, "site": got.get("site") or site[0], "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages": got["pages"],
        "coverage": {"comments_found": got["found"], "comments_expected": got["expected"], "notes": got["notes"]},
        "credits_used": client.credits_used - before,
        "thread": got["thread"],
    }
    if client.credits_remaining is not None:
        bundle["credits_remaining"] = client.credits_remaining
    return bundle


def analyse(bundle, work_dir, *, similar_text=True):
    """Convert a bundle into the two CSV files in work_dir and run the core on them."""
    from ..convert import write
    from ..core import analyze
    from ..load import InputError
    comments_path, profiles_path, warnings = write(bundle, work_dir)
    try:
        result = analyze(comments_path, profiles_path, similar_text=similar_text)
    except InputError as e:
        if not (similar_text and "similar-text" in str(e)):
            raise
        # the model is missing and there is no network: a run without the reworded-copies signal is still worth having
        warnings = warnings + [f"similar-text signal skipped: {e}"]
        result = analyze(comments_path, profiles_path, similar_text=False)
    thread = bundle.get("thread") or {}
    result["source"]["comments_file"] = thread.get("label") or bundle["url"]
    if profiles_path and thread.get("histories_ok"):
        result["source"]["profiles_file"] = f"recent posts of {thread['histories_ok']} participants"
    result["warnings"] = warnings + result["warnings"]    # warnings already hold the coverage notes
    _explain_collection(result, bundle)
    return result


PARTIAL_SHARE = 0.8   # reason partial_thread when fewer than this share of the comments the site counts could be read


def _explain_collection(result, bundle):
    """result.collection: what was read of the thread and whose history was fetched; adds the matching reasons."""
    thread, coverage = bundle.get("thread") or {}, bundle.get("coverage") or {}
    found, expected = coverage.get("comments_found"), coverage.get("comments_expected")
    commenters, fetched = thread.get("commenters"), thread.get("commenters_fetched")
    result["collection"] = {
        "platform": thread.get("platform"), "comments_found": found, "comments_expected": expected,
        "comments_hidden": thread.get("comments_hidden"), "commenters": commenters, "commenters_fetched": fetched,
        "histories_ok": thread.get("histories_ok"), "histories_failed": thread.get("histories_failed"),
        "history_per_commenter": thread.get("history_per_commenter"), "credits_used": bundle.get("credits_used")}
    reasons = result.setdefault("diagnostics", {}).setdefault("reasons", [])
    if found is not None and expected and found < PARTIAL_SHARE * expected:
        reasons.insert(0, {"code": "partial_thread", "text":
                           f"Only {found} of the {expected} comments the site counts could be read (the others are "
                           "deleted, hidden, blocked or beyond what the site returns)."})
    if commenters and fetched is not None and fetched < commenters:
        reasons.insert(0, {"code": "capped_histories", "text":
                           f"Other posts were fetched for {fetched} of {commenters} commenters; the rest are judged on "
                           "this thread only."})


def run(url, *, similar_text=True, **collect_options):
    """collect -> convert -> analyse. Returns (result, bundle). Every failure is a CollectError."""
    from ..convert import ConvertError
    from ..load import InputError
    bundle = collect(url, **collect_options)
    with tempfile.TemporaryDirectory(prefix="swarm-collect-") as work:
        try:
            return analyse(bundle, work, similar_text=similar_text), bundle
        except (ConvertError, InputError) as e:    # e.g. a thread with no comments
            raise CollectError(str(e)) from None
