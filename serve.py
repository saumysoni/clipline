"""
Pit Crew on a server: `python serve.py` (the systemd service in deploy/ runs this). `python app.py` stays the way to
run it on your own computer.

Waitress, ONE process with threads, never several processes: the vlog queue, the Instagram scheduler and the storage
clean-up are threads inside this process (CLAUDE.md gotcha 19), so a second process would run them twice. Caddy (deploy/
Caddyfile) is in front: it does https and hands requests to this port on the same machine only.

Settings (.env): PORT (8000), WEB_THREADS (16: requests at once; long work like making Shorts runs in its own threads,
not these), and TRUST_PROXY=1 because Caddy is in front (see web/server.py).
"""
import os

from waitress import serve

import app as pitcrew  # loads .env and every route, and starts the background threads

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    threads = int(os.getenv("WEB_THREADS", "16"))
    print(f"Pit Crew is running on 127.0.0.1:{port} with {threads} request threads (Caddy serves it over https).")
    serve(pitcrew.app, host="127.0.0.1", port=port, threads=threads,
          ident=None,                               # no "Server: waitress" header
          max_request_body_size=70 * 1024 * 1024,   # video pieces are 8 MB; Flask allows 64 MB (web/server.py)
          channel_timeout=300,                      # slow phone connections sending an 8 MB piece
          connection_limit=500)
