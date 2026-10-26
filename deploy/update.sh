#!/usr/bin/env bash
# Pit Crew: put the latest main on the server. Run as root:   sudo bash /opt/pitcrew/app/deploy/update.sh
#
# 1. Stops if code on the server was edited by hand (changes belong in GitHub).
# 2. Backs up the database.
# 3. Moves the code to the latest main, installs new Python packages if requirements.txt changed, checks every
#    Python file compiles and runs the automated tests (tests/). A Python error or a failed test stops here, before
#    any restart: Pit Crew keeps running the old version.
# 4. Restarts and waits up to 2 minutes for Pit Crew to answer.
# If anything fails after the code moved, it goes back to the version that was running (code, packages, restart)
# and says so. Vlogs being made during a restart are queued again automatically (web/store.py).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash $0"; exit 1; }
# bash reads a script while it runs, and this one changes the code folder it lives in: run from a copy
if [ -z "${PITCREW_UPDATE_COPY:-}" ]; then
  COPY=$(mktemp /tmp/pitcrew-update.XXXXXX.sh); cp "$0" "$COPY"
  PITCREW_UPDATE_COPY=1 exec bash "$COPY" "$@"
fi
trap 'rm -f "$0"' EXIT
APP=/opt/pitcrew/app
VENV=/opt/pitcrew/venv
BRANCH="${BRANCH:-main}"
COMPILE_SKIP='/(_backups|_test|\.venv)/'

say() { printf '\n\033[1;31m==>\033[0m \033[1m%s\033[0m\n' "$*"; }

healthy() {
  for _ in $(seq 1 60); do
    curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

if [ -n "$(git -C "$APP" status --porcelain --untracked-files=no)" ]; then
  echo "Files in $APP were changed on the server, so nothing was updated:"
  git -C "$APP" status --short --untracked-files=no | sed 's/^/  /'
  echo "Changes belong in GitHub (saumya -> pull request -> main). To drop the server's copies:"
  echo "  sudo git -C $APP checkout -- .    then run this again."
  exit 1
fi

OLD=$(git -C "$APP" rev-parse HEAD)
say "Getting the latest $BRANCH"
git -C "$APP" fetch -q origin "$BRANCH"
NEW=$(git -C "$APP" rev-parse "origin/$BRANCH")
if [ "$OLD" = "$NEW" ]; then
  echo "  Already up to date ($(git -C "$APP" log -1 --format='%h %s' HEAD))."
  exit 0
fi
git -C "$APP" log --oneline "$OLD..$NEW" | sed 's/^/  /'

say "Backing up the database first"
bash "$APP/deploy/backup.sh"

RESTARTED=""
back_to_old() {   # the code, its packages and (if it was restarted) the running service, as they were
  trap - ERR
  say "Going back to the version that was running ($(git -C "$APP" log -1 --format='%h %s' "$OLD"))"
  git -C "$APP" checkout -q -f -B "$BRANCH" "$OLD"   # moves the branch too, so the next update starts from here
  "$VENV/bin/pip" install -q -r "$APP/requirements.txt" || true
  if [ -n "$RESTARTED" ]; then
    systemctl restart pitcrew
    healthy && echo "  Pit Crew is running the old version again." \
            || echo "  Pit Crew still isn't answering. See: sudo journalctl -u pitcrew -n 100 --no-pager"
  else
    echo "  Pit Crew wasn't restarted, so it kept running the old version throughout."
  fi
  echo "  The new version needs fixing in GitHub before you try again."
  exit 1
}
trap back_to_old ERR

git -C "$APP" checkout -q -B "$BRANCH" "$NEW"
if ! git -C "$APP" diff --quiet "$OLD" "$NEW" -- requirements.txt; then
  say "requirements.txt changed: installing packages"
  "$VENV/bin/pip" install -q -r "$APP/requirements.txt"
fi
if ! "$VENV/bin/python" -m compileall -q -x "$COMPILE_SKIP" "$APP" >/dev/null 2>&1; then
  say "The new version has a Python error, so Pit Crew wasn't restarted"
  "$VENV/bin/python" -m compileall -q -x "$COMPILE_SKIP" "$APP" 2>&1 | grep -vE "^(Listing|Compiling)" | head -n 15 | sed 's/^/  /' || true
  back_to_old
fi
if [ -d "$APP/tests" ]; then   # the automated tests (tests/: throwaway folders, no internet, a few seconds)
  if ! (cd "$APP" && PYTHONDONTWRITEBYTECODE=1 timeout 600 "$VENV/bin/python" -W ignore -m unittest discover -s tests -t . \
        >/tmp/pitcrew-tests.log 2>&1); then
    say "The new version failed its tests, so Pit Crew wasn't restarted"
    grep -E "^(FAIL|ERROR):|^[A-Za-z]*(Error|Exception): " /tmp/pitcrew-tests.log | head -n 15 | sed 's/^/  /' || true
    echo "  Full output: /tmp/pitcrew-tests.log"
    back_to_old
  fi
  echo "  tests passed"
fi
# Server files that live outside the code folder (only when they changed)
for f in pitcrew.service pitcrew-backup.service pitcrew-backup.timer; do
  cmp -s "$APP/deploy/$f" "/etc/systemd/system/$f" || { install -m 644 "$APP/deploy/$f" "/etc/systemd/system/$f"; echo "  updated $f"; }
done
systemctl daemon-reload

say "Restarting Pit Crew"
RESTARTED=1
systemctl restart pitcrew
if healthy; then
  trap - ERR
  say "Updated to $(git -C "$APP" log -1 --format='%h %s')"
  exit 0
fi
say "Pit Crew didn't come back after the restart"
journalctl -u pitcrew -n 30 --no-pager -o cat | sed 's/^/  /'
back_to_old
