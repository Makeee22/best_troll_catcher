"""YouTube: a video's comments and replies, the channel's comments on its other videos (the only "history" the API
has: it cannot list one account's comments), and each commenter's channel creation date. YouTube Data API v3 with
the key in YOUTUBE_API_KEY (free; 10,000 quota units a day, about 130 per link). The key is never written to the
bundle: page urls are stored without it.

Bundle pages: {"youtube_video": the video, "threads": [commentThread, ...]} (replies beyond the 5 inline ones merged
into each thread's replies.comments), {"youtube_threads": [...]} for the channel, {"youtube_channels": [...]} for
the commenters. swarm.convert (sites.from_json) reads them.
"""
import os
import re
from urllib.parse import parse_qs, urlparse

from .contextdev import CollectError

API = "https://www.googleapis.com/youtube/v3/"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
THREAD_PAGES = 20      # 100 top-level comments each
REPLY_FETCHES = 100    # threads with more replies than the 5 that come inline
CHANNEL_PAGES = 10     # the channel's comment threads on all its videos, newest first
CHANNELS_PER_CALL = 50
MAX_PARTICIPANTS = 500


def _video_id(url):
    u = urlparse(url)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.").removeprefix("music.")
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host == "youtube.com":
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"^/(?:shorts|live|embed)/([^/?#]+)", u.path)
            vid = m.group(1) if m else ""
    else:
        return None
    return vid if VIDEO_ID.match(vid or "") else None


def matches(url):
    return _video_id(url) is not None


def _key():
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise CollectError("YouTube links need a YouTube Data API key (YOUTUBE_API_KEY) on the server.")
    return key


def _get(client, path, key):
    """(url without the key, response)."""
    data = client.direct_json(f"{API}{path}&key={key}")
    return f"{API}{path}", data


def _pages(client, path, key, pages):
    """Items of up to `pages` pages of a list request, following nextPageToken; (first url, items)."""
    first_url, items, token = None, [], None
    for _ in range(pages):
        url, data = _get(client, path + (f"&pageToken={token}" if token else ""), key)
        first_url = first_url or url
        items += [i for i in (data.get("items") or []) if isinstance(i, dict)]
        token = data.get("nextPageToken")
        if not token:
            break
    return first_url, items


def _author(comment):
    return ((comment.get("snippet") or {}).get("authorChannelId") or {}).get("value")


def collect(url, client, history, max_participants, on_progress):
    vid, key = _video_id(url), _key()
    try:
        video_url, video = _get(client, f"videos?part=snippet,statistics&id={vid}", key)
    except CollectError:
        raise CollectError("YouTube did not answer (the key may be wrong, or today's API quota is used up).") from None
    item = (video.get("items") or [None])[0]
    if not isinstance(item, dict):
        raise CollectError("That YouTube video was not found, or it is private.")
    snippet, stats = item.get("snippet") or {}, item.get("statistics") or {}
    try:
        threads_url, threads = _pages(client, f"commentThreads?part=snippet,replies&videoId={vid}&maxResults=100"
                                              "&order=time&textFormat=plainText", key, THREAD_PAGES)
    except CollectError:
        raise CollectError("YouTube refused this video's comments: they may be turned off, or today's API quota is "
                           "used up.") from None

    short = [t for t in threads if (t.get("snippet") or {}).get("totalReplyCount", 0)
             > len((t.get("replies") or {}).get("comments") or [])][:REPLY_FETCHES]
    for n, t in enumerate(short, 1):
        try:
            _, replies = _pages(client, f"comments?part=snippet&parentId={t['id']}&maxResults=100&textFormat=plainText", key, 1)
            t["replies"] = {"comments": replies}
        except Exception:            # one thread failing keeps its inline replies
            pass
        if on_progress:
            on_progress(n, len(short) + 1)

    pages = [{"url": threads_url, "role": "thread", "json": {"youtube_video": item, "threads": threads}}]
    channel, failed = snippet.get("channelId"), 0
    if channel:
        try:
            ch_url, ch_threads = _pages(client, f"commentThreads?part=snippet,replies&allThreadsRelatedToChannelId={channel}"
                                                "&maxResults=100&textFormat=plainText", key, CHANNEL_PAGES)
            pages.append({"url": ch_url, "role": "profile", "json": {"youtube_threads": ch_threads}})
        except Exception:
            failed = 1
    if on_progress:
        on_progress(len(short) + 1, len(short) + 1)

    comments = [t["snippet"]["topLevelComment"] for t in threads if (t.get("snippet") or {}).get("topLevelComment")]
    comments += [r for t in threads for r in ((t.get("replies") or {}).get("comments") or [])]
    authors = list(dict.fromkeys(a for a in map(_author, comments) if a))
    fetch = authors[:max_participants]
    for i in range(0, len(fetch), CHANNELS_PER_CALL):
        try:
            u, d = _get(client, f"channels?part=snippet&id={','.join(fetch[i:i + CHANNELS_PER_CALL])}", key)
            pages.append({"url": u, "role": "profile", "json": {"youtube_channels": d.get("items") or []}})
        except Exception:            # creation dates are supporting evidence only
            pass

    expected = int(stats.get("commentCount") or 0) or None
    notes = ["thread: YouTube cannot list one account's comments; the channel's comments on its other videos stand in "
             "for the commenters' histories"]
    if expected and len(comments) < expected:
        notes.append(f"thread: YouTube counts {expected} comments, {len(comments)} could be read (newest first, at "
                     f"most {THREAD_PAGES * 100} threads; held for review, removed or spam-filtered ones are not public)")
    if failed:
        notes.append("thread: the channel's other comments could not be fetched")
    return {
        "pages": pages, "notes": notes, "found": len(comments), "expected": expected,
        "thread": {"platform": "YouTube", "label": f"YouTube video {vid}", "url": url, "post_id": vid,
                   "title": snippet.get("title") or "", "author": snippet.get("channelTitle"),
                   "commenters": len(authors), "commenters_fetched": len(authors) if channel and not failed else 0,
                   "history_per_commenter": 0, "histories_ok": 0 if failed or not channel else len(authors),
                   "histories_failed": len(authors) if failed else 0},
    }
