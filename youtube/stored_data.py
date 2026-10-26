"""
YouTube numbers Pit Crew keeps in memory (Analytics caches, first-week views, Pit Crew's daily read), tidied by
web/youtube_upkeep.py once a day so nothing is kept longer than YouTube's rules allow (Developer Policies III.E.4):
anything no longer used is dropped, nothing is older than MAX_AGE, and a channel that's gone is forgotten at once.
"""
import time

from youtube import analytics, analytics_coach, analytics_more

MAX_AGE = 30 * 24 * 3600


def forget_old_numbers(gone_channels=(), now=None):
    """Drop expired cache entries, numbers older than MAX_AGE, and everything about gone_channels. Returns how many."""
    now = now or time.time()
    gone = set(gone_channels)
    n = 0
    for mod in (analytics, analytics_more):  # (time saved, numbers): used for CACHE_SECS, then only taking memory
        with mod._LOCK:
            for k in [k for k, v in mod._CACHE.items() if now - v[0] >= analytics.CACHE_SECS or set(k) & gone]:
                mod._CACHE.pop(k, None)
                n += 1
    with analytics._LOCK:  # first-week views: (channel, video id) -> (time asked, views, complete)
        for k in [k for k, v in analytics._WEEK.items() if now - v[0] >= MAX_AGE or k[0] in gone]:
            analytics._WEEK.pop(k, None)
            n += 1
    with analytics_coach._LOCK:  # the daily read: key -> (expires at, read); the key holds the channel id
        for k in [k for k, v in analytics_coach._CACHE.items()
                  if now >= v[0] or set(k if isinstance(k, tuple) else (k,)) & gone]:
            analytics_coach._CACHE.pop(k, None)
            n += 1
    return n
