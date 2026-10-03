"""
Reading From/To times typed by the creator.
"""
import pipeline


def read_times(start, end, label="the moment"):
    """(start, end) in seconds from what the creator typed, None if both are empty.
    Raises RuntimeError with a plain message if they don't make sense."""
    start, end = str(start or "").strip(), str(end or "").strip()
    if not start and not end:
        return None
    s, e = pipeline.parse_time(start), pipeline.parse_time(end)
    if s is None or e is None:
        raise RuntimeError(f"Type both times for {label} like 2:10 (minutes:seconds), for example From 2:10 To 2:45.")
    if e <= s:
        raise RuntimeError(f"For {label}, the To time has to be after the From time.")
    return s, e
