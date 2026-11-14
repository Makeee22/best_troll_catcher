"""Collector: a link to a discussion -> the raw bundle of docs/collect-interface.md -> swarm.convert -> swarm.core.

    bundle = collect(url)                  # fetch the thread, each commenter's recent history, and note what is missing
    result, bundle = run(url)              # ... then convert and analyse

Needs the network; swarm.core never imports this package. Context.dev (key CONTEXT_DEV_API_KEY) is used where
a site needs it; Bluesky and Hacker News also work without a key, through their public APIs.
"""
import re
import tempfile
from datetime import datetime, timezone

from . import bluesky, hackernews, reddit
from .contextdev import CollectError, ContextDev, ContextDevError

__all__ = ["collect", "run", "analyse", "CollectError", "ContextDev", "ContextDevError"]

SITES = [("bluesky", bluesky), ("hackernews", hackernews), ("reddit", reddit)]


def _normalise(url):
    url = (url or "").strip()
    if len(url) > 500 or any(c.isspace() for c in url):
        raise CollectError("That does not look like a link.")
    return url if re.match(r"^https?://", url, re.I) else "https://" + url


def collect(url, *, history=25, max_participants=150, on_progress=None, client=None):
    """The raw bundle for a link (docs/collect-interface.md). Raises CollectError with a message for the user."""
    url = _normalise(url)
    site = next(((name, mod) for name, mod in SITES if mod.matches(url)), None)
    if site is None:
        raise CollectError(f"This site is not supported yet: {re.sub(r'^https?://', '', url).split('/')[0]}")
    client = client or ContextDev.from_env()
    before = client.credits_used
    got = site[1].collect(url, client, history, max_participants, on_progress)
    bundle = {
        "url": url, "site": site[0], "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    comments_path, profiles_path, warnings = write(bundle, work_dir)
    result = analyze(comments_path, profiles_path, similar_text=similar_text)
    thread = bundle.get("thread") or {}
    result["source"]["comments_file"] = thread.get("label") or bundle["url"]
    if profiles_path and thread.get("histories_ok"):
        result["source"]["profiles_file"] = f"recent posts of {thread['histories_ok']} participants"
    result["warnings"] = warnings + result["warnings"]    # warnings already hold the coverage notes
    return result


def run(url, *, similar_text=True, **collect_options):
    """collect -> convert -> analyse. Returns (result, bundle)."""
    bundle = collect(url, **collect_options)
    with tempfile.TemporaryDirectory(prefix="swarm-collect-") as work:
        return analyse(bundle, work, similar_text=similar_text), bundle
