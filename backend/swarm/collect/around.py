"""Shared by the collectors: whose history to fetch first, and the time window around the thread (handoff R2, R3)."""
from collections import Counter
from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 7   # a history is taken from the thread's date +- this many days, not the newest posts of today
FREE_PARTICIPANTS = 500   # public APIs cost no credits; Reddit (Context.dev) keeps a lower cap


def most_active(authors):
    """Distinct authors, most posts in the thread first; ties keep the order they first appear in."""
    counts = Counter(authors)
    return sorted(dict.fromkeys(authors), key=lambda a: -counts[a])


def when(value):
    """An ISO 8601 time (Z or an offset) or epoch seconds as an aware datetime; None when unreadable."""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def window(start):
    """(from, to) around the thread's start, or None without a start time."""
    return None if start is None else (start - timedelta(days=WINDOW_DAYS), start + timedelta(days=WINDOW_DAYS))
