"""
Long background work gives way to the pages: making Shorts (transcription, FFmpeg, face finding), preparing a vlog
upload, the small scrubbing copy and a vlog's poster run at a lower CPU priority (nice BACKGROUND) than the threads that
answer the creator's clicks.

A small server has only a few processor cores, and a vlog being made used all of them at the same priority as everything
else: every page, the editor's previews and a Short being remade waited their turn behind it ("laggy on the server, fine
on my computer"). Now, when both want the processor, the clicks come first; when nothing else is going on the
background work still gets the whole machine, so it isn't any slower.

Linux only (the server): there a priority belongs to one thread, and the threads and programs it starts afterwards (the
speech model's workers, FFmpeg) get it too. Elsewhere (a Mac running app.py) this does nothing.
"""
import os
import sys
import threading

BACKGROUND = 10  # nice value (0 = normal, 19 = lowest)


def lower(level=BACKGROUND):
    """Run the rest of this thread, and what it starts from now on, at `level` (never raises it back up)."""
    if not sys.platform.startswith("linux"):
        return
    try:
        tid = threading.get_native_id()
        if os.getpriority(os.PRIO_PROCESS, tid) < level:
            os.setpriority(os.PRIO_PROCESS, tid, level)
    except (OSError, AttributeError):  # not allowed here: it simply runs at the normal priority
        pass


def background(fn):
    """fn wrapped to run at the background priority: threading.Thread(target=background(fn), ...)."""
    def run(*a, **kw):
        lower()
        return fn(*a, **kw)
    run.__name__ = getattr(fn, "__name__", "run")
    return run
