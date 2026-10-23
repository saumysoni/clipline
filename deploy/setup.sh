#!/usr/bin/env bash
# Pit Crew: set up a fresh Ubuntu 24.04 server (Arm or x86), or bring an existing one up to date. Run as root:
#
#   sudo bash deploy/setup.sh pitcrew.example.com you@example.com
#
# (the domain must already point at this server; the email is for the https certificate's expiry notices)
#
# Safe to run again: it keeps your .env values, your data and your certificate. See LAUNCH.md for the whole launch.
#
# What it does:
#   1. Installs FFmpeg (with captions support), Python, Caddy (https), fonts, SQLite and automatic security updates
#   2. Makes a "pitcrew" user that runs Pit Crew and owns only its data (/srv/pitcrew)
#   3. Gets the code (/opt/pitcrew/app, branch main) and its Python packages (/opt/pitcrew/venv)
#   4. Writes /opt/pitcrew/app/.env with the server's settings and new secrets (never overwriting yours)
#   5. Installs the Pit Crew service, Caddy's settings, daily database backups, log retention (30 days), swap,
#      and opens ports 80 and 443 in the server's own firewall
#   6. Downloads the speech model and starts Pit Crew, then checks it answers
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
REPO_URL="${REPO_URL:-https://github.com/saumysoni/clipline.git}"
BRANCH="${BRANCH:-main}"
APP=/opt/pitcrew/app
VENV=/opt/pitcrew/venv
DATA=/srv/pitcrew
ENVF="$APP/.env"
SKIP_SYSTEMD="${SKIP_SYSTEMD:-}"   # tests only: build everything but don't start services

say() { printf '\n\033[1;31m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mStopped:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "Run this as root: sudo bash deploy/setup.sh <domain> <email>"
[[ "$DOMAIN" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] || die "Give your domain first, e.g.: sudo bash deploy/setup.sh pitcrew.example.com you@example.com"
[[ "$EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || die "Give an email address second (for the https certificate's notices)."
. /etc/os-release
[ "${ID:-}" = ubuntu ] || die "This script is for Ubuntu (24.04). This server runs ${PRETTY_NAME:-something else}."

export DEBIAN_FRONTEND=noninteractive

say "1/6  Installing system packages"
apt-get update -q
apt-get install -y -q --no-install-recommends ca-certificates curl gnupg git ffmpeg sqlite3 \
  python3 python3-venv python3-dev build-essential fonts-montserrat fonts-dejavu-core \
  unattended-upgrades iptables-persistent debian-keyring debian-archive-keyring apt-transport-https
FILTERS=$(ffmpeg -hide_banner -filters 2>/dev/null || true)   # (not piped into grep -q: with pipefail that fails)
grep -q " subtitles " <<<"$FILTERS" || die "This FFmpeg can't add captions (no libass)."
if ! command -v caddy >/dev/null; then
  if curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
     && curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list; then
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
  fi
  apt-get install -y -q caddy   # Caddy's own repository, else Ubuntu's copy
fi
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

say "2/6  The pitcrew user and its folders"
id pitcrew >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin pitcrew
install -d -o pitcrew -g pitcrew -m 750 "$DATA" "$DATA/data" "$DATA/jobs" "$DATA/models" "$DATA/backups"
install -d -m 755 /opt/pitcrew
# the person who ran setup (e.g. "ubuntu") can read the backups (to copy them off the server)
[ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ] && usermod -aG pitcrew "$SUDO_USER" || true

say "3/6  Getting the code ($BRANCH) and its Python packages"
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch -q origin "$BRANCH"
  git -C "$APP" checkout -q "$BRANCH"
  git -C "$APP" pull -q --ff-only origin "$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$APP"
fi
install -d -m 755 "$APP/fonts"
MONT=$(find /usr/share/fonts -iname 'Montserrat-ExtraBold.*' | head -n 1)
[ -n "$MONT" ] && { [ -f "$APP/fonts/$(basename "$MONT")" ] || cp "$MONT" "$APP/fonts/"; } || echo "  (Montserrat ExtraBold not found: captions use another bold font)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP/requirements.txt"
"$VENV/bin/python" -m compileall -q "$APP" >/dev/null || true

say "4/6  Settings (.env)"
CORES=$(nproc)
if [ ! -f "$ENVF" ]; then
  cp "$APP/.env.example" "$ENVF"
  # A new .env: the server's tuning replaces the laptop defaults in .env.example (one vlog at a time on a small
  # server, transcription on every core in the processor's fastest number format, a monthly allowance per creator).
  # On later runs these are left alone, so your own changes stay.
  "$VENV/bin/python" "$APP/deploy/envtool.py" "$ENVF" --force \
    "JOB_SLOTS=$(( CORES >= 8 ? 2 : 1 ))" "WHISPER_DEVICE=cpu" "WHISPER_COMPUTE_TYPE=int8" "WHISPER_THREADS=$CORES" \
    "MONTHLY_VLOG_MINUTES=600" "MAX_VLOG_MINUTES=120" "INVITE_ONLY=1" "CAPTION_FONT=Montserrat ExtraBold"
fi
"$VENV/bin/python" "$APP/deploy/envtool.py" "$ENVF" \
  "APP_URL=https://$DOMAIN" "PUBLIC_URL=https://$DOMAIN" \
  "YOUTUBE_REDIRECT_URI=https://$DOMAIN/api/youtube/callback" \
  "INSTAGRAM_REDIRECT_URI=https://$DOMAIN/api/instagram/callback" \
  "SESSION_COOKIE_SECURE=1" "TRUST_PROXY=1" \
  "DATABASE_PATH=$DATA/data/clipline.db" "JOBS_DIR=$DATA/jobs" \
  "SECRET_KEY=$("$VENV/bin/python" -c 'import secrets; print(secrets.token_hex(32))')" \
  "TOKEN_KEY=$("$VENV/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  "INVITE_ONLY=1" "WHISPER_THREADS=$CORES"
chown root:pitcrew "$ENVF"; chmod 640 "$ENVF"
touch "$DATA/data/invites.txt"; chown pitcrew:pitcrew "$DATA/data/invites.txt"; chmod 640 "$DATA/data/invites.txt"

say "5/6  Service, https, backups, logs, swap, firewall"
sed -e "s/PITCREW_DOMAIN/$DOMAIN/" -e "s/PITCREW_EMAIL/$EMAIL/" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
install -m 644 "$APP/deploy/pitcrew.service" /etc/systemd/system/pitcrew.service
install -m 644 "$APP/deploy/pitcrew-backup.service" /etc/systemd/system/pitcrew-backup.service
install -m 644 "$APP/deploy/pitcrew-backup.timer" /etc/systemd/system/pitcrew-backup.timer
install -d -m 755 /etc/systemd/journald.conf.d
printf '[Journal]\nMaxRetentionSec=30day\nSystemMaxUse=1G\n' > /etc/systemd/journald.conf.d/pitcrew.conf   # privacy policy: logs <= 30 days
if [ -z "$(swapon --show 2>/dev/null)" ] && [ ! -f /swapfile ]; then   # 4 GB of swap: a safety net for memory peaks
  if fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile; then
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  else
    rm -f /swapfile; echo "  (couldn't add swap; fine on a 12 GB server)"
  fi
fi
# Oracle's Ubuntu images block everything but SSH in the server's own firewall (iptables); open http and https
for t in iptables ip6tables; do
  if command -v $t >/dev/null && ! $t -C INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
    $t -I INPUT 1 -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null || true
  fi
done
command -v netfilter-persistent >/dev/null && netfilter-persistent save >/dev/null 2>&1 || true
command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q active && ufw allow 80,443/tcp >/dev/null || true

say "6/6  Speech model and start"
WMODEL=$("$VENV/bin/python" "$APP/deploy/envtool.py" "$ENVF" --get WHISPER_MODEL); WMODEL=${WMODEL:-small}
sudo -u pitcrew HF_HOME="$DATA/models" "$VENV/bin/python" -c \
  "from faster_whisper import WhisperModel; WhisperModel('$WMODEL', device='cpu', compute_type='int8')" >/dev/null 2>&1 \
  && echo "  speech model '$WMODEL' ready" || echo "  (couldn't download the speech model now; the first vlog will)"
if [ -z "$SKIP_SYSTEMD" ]; then
  systemctl daemon-reload
  systemctl restart systemd-journald
  systemctl enable --now pitcrew-backup.timer >/dev/null
  systemctl enable pitcrew >/dev/null
  systemctl restart pitcrew
  systemctl enable caddy >/dev/null
  systemctl reload caddy 2>/dev/null || systemctl restart caddy
  ok=""
  for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  [ -n "$ok" ] || die "Pit Crew didn't start. See why: sudo journalctl -u pitcrew -n 50 --no-pager"
fi

say "Done. Pit Crew is running."
echo "  Open: https://$DOMAIN/welcome  (the certificate can take a minute the first time)"
MISSING=$("$VENV/bin/python" "$APP/deploy/envtool.py" "$ENVF" --empty GEMINI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET \
  SUPPORT_EMAIL OPERATOR_NAME SMTP_HOST SMTP_USER SMTP_PASSWORD MAIL_FROM INSTAGRAM_APP_ID INSTAGRAM_APP_SECRET | tr '\n' ' ')
if [ -n "${MISSING// /}" ]; then
  echo "  Still to fill in $ENVF (sudo nano $ENVF, then: sudo systemctl restart pitcrew):"
  echo "    $MISSING"
fi
echo "  Invite someone:   sudo bash $APP/deploy/invite.sh friend@example.com"
echo "  Update later:     sudo bash $APP/deploy/update.sh"
echo "  Check on it:      sudo bash $APP/deploy/status.sh"
echo "  Back up these once, somewhere safe (not on this server): $ENVF (holds SECRET_KEY and TOKEN_KEY)"
