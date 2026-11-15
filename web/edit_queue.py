"""
Edits saved in the editor take turns on the whole server: at most SLOTS Shorts are rendered again at once (Save on
captions, Reframe, text, Trim, a hook, Try again / Add a Short). Each render already uses every core (FFmpeg) and about
0.5-1 GB of memory with a 4K vlog, so five creators pressing Save together ran five at once: all five slower, memory up
by several GB, the pages slow meanwhile, and enough of them could run the server out of memory. Now SLOTS run at full
speed and the rest wait in order, their Short saying "Waiting for another edit to finish" until their turn.

Edits to one vlog already went one at a time (store.RETRY_LOCKS); this is across vlogs. Making Shorts from a new vlog
has its own queue (web/job_queue.py, at the background priority); redrawing a thumbnail is light and doesn't wait.

SLOTS: EDIT_SLOTS in .env, else half the processor cores (1 on 2 cores, 2 on the e2-standard-4's 4, at most 4).
"""
import os
import threading
from contextlib import contextmanager

WAITING_MSG = "Waiting for another edit to finish"


def _slots():
    try:
        n = int(os.getenv("EDIT_SLOTS", "0"))
    except ValueError:
        n = 0
    if n <= 0:
        from pipeline.transcribe import available_cpus
        n = min(4, max(1, available_cpus() // 2))
    return n


SLOTS = _slots()
_TURNS = threading.BoundedSemaphore(SLOTS)
_LOCK = threading.Lock()
WAITING = []  # (job id, idx) in the order they asked: who waits (for tests and /healthz-style checks)


def _say(job_id, idx, msg):
    """The Short's progress line; never stops the queue (its vlog may have been deleted meanwhile)."""
    from web.store import update_short
    try:
        update_short(job_id, idx, retry_msg=msg)
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def turn(job_id, idx):
    """Render inside this: waits for a free slot (saying so on the Short meanwhile), always gives it back."""
    from web.store import JOBS, LOCK
    if not _TURNS.acquire(blocking=False):
        with LOCK:
            me = next((s for s in (JOBS.get(job_id) or {}).get("shorts") or [] if s.get("idx") == idx), {})
            said = me.get("retry_msg")
        with _LOCK:
            WAITING.append((job_id, idx))
        try:
            _say(job_id, idx, WAITING_MSG)
            _TURNS.acquire()
        finally:
            with _LOCK:
                WAITING.remove((job_id, idx))
        _say(job_id, idx, said)
    try:
        yield
    finally:
        _TURNS.release()
