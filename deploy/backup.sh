#!/usr/bin/env bash
# Pit Crew: back up the accounts database (every account, connection and saved Reel number) and the invite list.
# Runs every night (pitcrew-backup.timer) and before every update. Keeps 14 days in /srv/pitcrew/backups.
#
# NOT in the backup, on purpose: .env (SECRET_KEY, TOKEN_KEY). The YouTube/Instagram tokens in the database are
# encrypted with TOKEN_KEY, so a backup alone can't be used to reach anyone's accounts. Keep a copy of .env somewhere
# safe that isn't this server (LAUNCH.md). Vlogs and clips (/srv/pitcrew/jobs) aren't backed up: they're big and
# short-lived (see the privacy policy's "How long we keep it").
#
# To copy backups off the server, from your own computer:
#   scp -r ubuntu@<server>:/srv/pitcrew/backups ./pitcrew-backups
set -euo pipefail
DATA=/srv/pitcrew
OUT="$DATA/backups"
KEEP_DAYS=14
STAMP=$(date -u +%Y%m%d-%H%M%S)
DB=$(grep -E '^DATABASE_PATH=' /opt/pitcrew/app/.env 2>/dev/null | cut -d= -f2-)
DB=${DB:-$DATA/data/clipline.db}

install -d -o pitcrew -g pitcrew -m 750 "$OUT"
if [ -f "$DB" ]; then
  TMP="$OUT/.db-$STAMP.sqlite"
  sqlite3 "$DB" ".backup '$TMP'"                      # a consistent copy, even while Pit Crew is writing
  [ "$(sqlite3 "$TMP" 'PRAGMA integrity_check;')" = ok ] || { rm -f "$TMP"; echo "Backup failed its check"; exit 1; }
  gzip -c "$TMP" > "$OUT/db-$STAMP.sqlite.gz" && rm -f "$TMP"
  echo "  database: $OUT/db-$STAMP.sqlite.gz ($(du -h "$OUT/db-$STAMP.sqlite.gz" | cut -f1))"
fi
[ -f "$DATA/data/invites.txt" ] && cp "$DATA/data/invites.txt" "$OUT/invites-$STAMP.txt"
chown pitcrew:pitcrew "$OUT"/* 2>/dev/null || true
chmod 640 "$OUT"/* 2>/dev/null || true
find "$OUT" -maxdepth 1 -type f \( -name 'db-*.sqlite.gz' -o -name 'invites-*.txt' \) -mtime +$KEEP_DAYS -delete
