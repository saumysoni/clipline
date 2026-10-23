#!/usr/bin/env bash
# Pit Crew private beta: let someone make an account (no restart needed). Run as root:
#   sudo bash /opt/pitcrew/app/deploy/invite.sh friend@example.com ["a note, e.g. their name"]
#   sudo bash /opt/pitcrew/app/deploy/invite.sh --list
# They can then sign up with that email, or with "Continue with Google" if that's their Google address.
# For YouTube to work for them before Google approves the app, also add the same address as a test user in Google
# Cloud (LAUNCH.md, "Add a tester"); for Instagram, add their Instagram account as a tester in the Meta app.
set -euo pipefail
F=/srv/pitcrew/data/invites.txt
[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash $0 <email>"; exit 1; }
touch "$F"; chown pitcrew:pitcrew "$F"; chmod 640 "$F"
if [ "${1:-}" = "--list" ]; then
  grep -v '^\s*#' "$F" | sed '/^\s*$/d' || echo "(nobody invited yet)"
  exit 0
fi
EMAIL=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | xargs)
[[ "$EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || { echo "Give an email address: sudo bash $0 friend@example.com"; exit 1; }
if awk -v e="$EMAIL" '{ sub(/#.*/, ""); gsub(/[ \t\r]/, ""); if (tolower($0) == e) f = 1 } END { exit !f }' "$F"; then
  echo "$EMAIL is already invited."
else
  printf '%s  # invited %s%s\n' "$EMAIL" "$(date -u +%F)" "${2:+, $2}" >> "$F"
  echo "Invited $EMAIL. They can sign up now."
fi
