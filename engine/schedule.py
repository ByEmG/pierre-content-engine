"""Posting slots in local time."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def next_slot(now: datetime, post_days: list[str], post_time: str, tz: str, taken: set[datetime] = frozenset()) -> datetime:
    """Next free posting slot strictly after `now` (aware datetime). Returns an aware datetime in tz."""
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    want = {DAYS.index(d) for d in post_days}
    t = _hm(post_time)
    for i in range(0, 60):
        day = (local + timedelta(days=i)).date()
        if day.weekday() not in want:
            continue
        slot = datetime.combine(day, t, tzinfo=zone)
        if slot > local and slot not in taken:
            return slot
    raise RuntimeError("No posting slot in the next 60 days; check schedule.post_days")


def draft_due(now: datetime, post_days: list[str], draft_time: str, tz: str) -> str | None:
    """If tomorrow is a post day and it is past draft_time today, return today's date key."""
    local = now.astimezone(ZoneInfo(tz))
    tomorrow = (local + timedelta(days=1)).weekday()
    if DAYS[tomorrow] in post_days and local.time() >= _hm(draft_time):
        return local.date().isoformat()
    return None
