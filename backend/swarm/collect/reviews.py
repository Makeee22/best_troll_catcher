"""Context.dev's prebuilt review and comment parsers: one call per link, no commenter histories.

The parser's `parsed` object goes into the bundle exactly as returned; swarm.convert (sites.from_parsed) reads it.
Only google-maps-reviews takes a `limit` (the others return one page).
"""
import re
from urllib.parse import urlparse

from .contextdev import CollectError

GOOGLE_MAPS_LIMIT = 200
# (host pattern, path pattern, parser, platform name)
PARSERS = [
    (r"(?:www\.|maps\.)?google\.[a-z.]+", r"/maps/place/", "google-maps-reviews", "Google Maps"),
    (r"apps\.apple\.com", r"/app/", "app-store-reviews", "App Store"),
    (r"play\.google\.com", r"/store/apps/details", "google-play-reviews", "Google Play"),
    (r"(?:www\.)?tripadvisor\.[a-z.]+", r"-Reviews-", "tripadvisor-reviews", "Tripadvisor"),
    (r"(?:www\.)?yelp\.[a-z.]+", r"/biz/", "yelp-reviews", "Yelp"),
    (r"(?:www\.)?g2\.com", r"/products/[^/]+/reviews", "g2-reviews", "G2"),
    (r"(?:www\.)?tiktok\.com", r"/@[^/]+/video/\d+", "tiktok-comments", "TikTok"),
]


def _find(url):
    u = urlparse(url)
    for host, path, parser, platform in PARSERS:
        if re.fullmatch(host, (u.hostname or "").lower()) and re.search(path, u.path):
            return parser, platform
    return None


def matches(url):
    return _find(url) is not None


def collect(url, client, history, max_participants, on_progress):
    parser, platform = _find(url)
    parsed = client.parse(url, parser, limit=GOOGLE_MAPS_LIMIT if parser == "google-maps-reviews" else None)
    if not isinstance(parsed, dict) or not parsed.get("success"):
        raise CollectError(f"Context.dev could not read the {platform} page ({(parsed or {}).get('error_code') or 'unknown error'}). "
                           "It may not be public, or the link may not be the page of one place, app or video.")
    data = parsed.get("data") or {}
    found = len(data.get("reviews") or data.get("comments") or [])
    meta = data.get("location") or data.get("business") or {}       # Tripadvisor and Yelp know the total
    expected = meta.get("review_count") if isinstance(meta.get("review_count"), int) else None
    notes = []
    if expected and expected > found:
        notes.append(f"thread: {found} of {expected} reviews were read (the parser returns one page)")
    return {
        "site": parser, "pages": [{"url": url, "role": "thread", "parsed": parsed}], "notes": notes,
        "found": found, "expected": expected,
        "thread": {"platform": platform, "label": f"{platform} reviews {url}", "title": None, "url": url, "post_id": None,
                   "commenters": None, "commenters_fetched": 0, "history_per_commenter": 0, "histories_ok": 0, "histories_failed": 0},
    }
