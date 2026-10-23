#!/usr/bin/env bash
# Pit Crew: how is the server doing?   sudo bash /opt/pitcrew/app/deploy/status.sh
APP=/opt/pitcrew/app
echo "Version:   $(git -C "$APP" log -1 --format='%h %s (%cr)' 2>/dev/null)"
echo "Service:   $(systemctl is-active pitcrew) (since $(systemctl show pitcrew -p ActiveEnterTimestamp --value 2>/dev/null))"
echo "Health:    $(curl -s http://127.0.0.1:8000/healthz || echo 'not answering')"
echo "https:     $(systemctl is-active caddy)"
echo "Disk:      $(df -h /srv/pitcrew | awk 'NR==2{print $4" free of "$2}')"
echo "Memory:    $(free -h | awk '/Mem:/{print $7" available of "$2}')"
echo "Vlogs:     $(find /srv/pitcrew/jobs -maxdepth 1 -mindepth 1 -type d -name '??????????' 2>/dev/null | wc -l) on disk"
echo "Accounts:  $(sqlite3 "file:/srv/pitcrew/data/clipline.db?mode=ro" 'SELECT COUNT(*) FROM users' 2>/dev/null || echo '?')"
echo "Invited:   $(grep -cvE '^\s*(#|$)' /srv/pitcrew/data/invites.txt 2>/dev/null || echo 0)"
echo "Backups:   $(ls -1t /srv/pitcrew/backups/db-*.sqlite.gz 2>/dev/null | head -n1 | xargs -r basename) (newest)"
echo
echo "Last problems in the log (24 h):"
journalctl -u pitcrew --since "24 hours ago" --no-pager -o cat 2>/dev/null | grep -iE "traceback|error|didn't work|couldn't" | tail -n 8 | sed 's/^/  /' || true
