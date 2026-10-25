#!/usr/bin/env bash
# Pit Crew: run the tests on the server, safely next to the live site. Run as root:
#
#   sudo bash /opt/pitcrew/app/deploy/test.sh             fast tests (what update.sh runs before every update), ~1 min
#   sudo bash /opt/pitcrew/app/deploy/test.sh system      the real FFmpeg pipeline + a real server process, ~5 min
#   sudo bash /opt/pitcrew/app/deploy/test.sh ab          A/B comparisons on this machine (incl. the speech model), ~5 min
#   sudo bash /opt/pitcrew/app/deploy/test.sh stress      a COPY of Pit Crew under load: 25 people for 60 s
#        ... stress --users 40 --seconds 120 --vlogs 2
#   sudo bash /opt/pitcrew/app/deploy/test.sh live --url https://<domain> --email <test account>
#                                                         a gentle, read-only check of the live site itself
#   sudo bash /opt/pitcrew/app/deploy/test.sh all         fast + system + ab + stress
#
# Everything except "live" runs as the pitcrew user on throwaway folders in /tmp, with YouTube, Instagram, the AI and
# email faked, and never reads .env: the live site's data, keys and accounts are never used, nothing is posted, and
# the folders are removed afterwards. Heavy suites run at low priority (nice 15), so the live site keeps the CPU; still,
# run system / ab / stress when few people are using Pit Crew (they take a few minutes of both cores).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash $0 $*"; exit 1; }
APP=/opt/pitcrew/app
VENV=/opt/pitcrew/venv
WHAT="${1:-fast}"
[ $# -gt 0 ] && shift

say() { printf '\n\033[1;31m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
run() {  # as the service's user, from the code folder (read-only to it), writing only to /tmp
  (cd "$APP" && runuser -u pitcrew -- env HOME=/tmp TMPDIR=/tmp PYTHONDONTWRITEBYTECODE=1 \
      PITCREW_HF_HOME=/srv/pitcrew/models nice -n 15 "$VENV/bin/python" -W ignore "$@")
}
fast()   { say "Fast tests";   run -m unittest discover -s tests -t .; }
system() { say "System tests (real FFmpeg, real server process)"; run -m unittest discover -s tests/system -t . -p "system_*.py"; }
ab()     { say "A/B comparisons"; run -m tests.ab.compare "$@"; }
stress() { say "Stress test (a copy of Pit Crew, not the live site)"; run -m tests.stress.stress local "$@"; }

case "$WHAT" in
  fast) fast ;;
  system) system ;;
  ab) ab "$@" ;;
  stress) stress "$@" ;;
  live) say "Live check (read-only)"; run -m tests.stress.stress live "$@" ;;
  all) fast && system && ab && stress ;;
  *) echo "Unknown: $WHAT. Use fast, system, ab, stress, live or all."; exit 1 ;;
esac
