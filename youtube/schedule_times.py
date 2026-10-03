"""
When each Short goes out: preset schedules or a custom start and spacing, in the creator's time zone.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SPACINGS = (6, 12, 24, 48, 72, 168)  # hours between Shorts that the custom schedule offers


MIN_LEAD = timedelta(minutes=15)  # a scheduled time closer than this may already be past by upload time


def zone(name):
    """The creator's time zone (the browser sends its name), or this computer's zone."""
    try:
        return ZoneInfo(name) if name else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo


def plan_times(n, mode, tz_name=None, start=None, every_hours=24):
    """Return n aware datetimes in the creator's time zone (or None for 'post now').

    Presets start tomorrow; "custom" starts at `start` ("YYYY-MM-DDTHH:MM", the creator's local time)
    and adds `every_hours` for each next Short. Raises RuntimeError if a custom time isn't usable."""
    tz = zone(tz_name)
    if mode == "now":
        return [None] * n
    if mode == "custom":
        try:
            first = datetime.fromisoformat(start or "").replace(tzinfo=tz)
        except ValueError:
            raise RuntimeError("Pick the date and time for the first Short.") from None
        if first < datetime.now(tz) + MIN_LEAD:
            raise RuntimeError("Pick a time at least 15 minutes from now.")
        if every_hours not in SPACINGS:
            every_hours = 24
        return [first + timedelta(hours=every_hours * k) for k in range(n)]
    day = (datetime.now(tz) + timedelta(days=1)).date()
    times = []
    for k in range(n):
        if mode == "two":
            d = day + timedelta(days=k // 2)
            times.append(datetime(d.year, d.month, d.day, 18 if k % 2 else 12, 0, tzinfo=tz))
        else:
            d = day + timedelta(days=k)
            hour = 12 if mode == "d12" else 18
            times.append(datetime(d.year, d.month, d.day, hour, 0, tzinfo=tz))
    return times
