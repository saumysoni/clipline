"""
Pit Crew's real server (serve.py: Waitress, one process) with only the outside world faked (tests/fakes.py), on a
throwaway database and jobs folder. Used by the system and stress tests, locally and on the server:

    python -m tests.system.fake_server            # PITCREW_TEST_PORT (default 8765); prints "READY <port>" when it answers
    PITCREW_REAL_MEDIA=1 ...                       # the real editing pipeline (FFmpeg), fake AI + transcription
"""
from tests import fakes as F  # first: clean settings, fakes, throwaway folders

import os
import signal
import sys
import threading
import time
import urllib.request

from waitress import serve


def main():
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))  # a normal stop removes the throwaway folders (atexit)
    port = int(os.getenv("PITCREW_TEST_PORT", "8765"))  # (not PORT: tests/_env.py clears every .env setting)
    flask_app = F.app()
    from web import accounts
    accounts.SIGNUPS_PER_HOUR = 10 ** 6  # stress tests sign many people up from one machine
    import accounts.mail as M

    def show(to, subject, text):  # emails are printed, so a test can open the confirmation link (Server.email_token)
        F.fake_send_email(to, subject, text)
        print(f"EMAIL to {to}: {subject}\n{text}\nEND EMAIL", flush=True)
    M.send_email = show

    def ready():
        for _ in range(200):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2).read()
                print(f"READY {port} {F.TMP}", flush=True)
                return
            except OSError:
                time.sleep(0.05)
    threading.Thread(target=ready, daemon=True).start()
    serve(flask_app, host="127.0.0.1", port=port, threads=int(os.getenv("WEB_THREADS", "16")), ident=None,
          max_request_body_size=70 * 1024 * 1024, channel_timeout=300, connection_limit=500, _quiet=True)


if __name__ == "__main__":
    sys.exit(main())
