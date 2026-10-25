#!/usr/bin/env bash
# Pit Crew: turn the old public pages in docs/ (GitHub Pages) into redirects to the live site's own pages.
# Run on your own computer, once the site answers over https:
#   bash deploy/point-docs.sh pitcrewapp.me
# then commit docs/ on your branch and open a pull request as usual. Running it again with another domain (a .com later)
# just points them there instead. demo.gif, demo.mp4 and logo.svg stay (the README uses them).
set -euo pipefail
DOMAIN="${1:-}"
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%%/*}"
if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]]; then
  echo "Give the site's domain, for example:  bash deploy/point-docs.sh pitcrewapp.me"; exit 1
fi
if ! curl -fsS -o /dev/null --max-time 15 "https://$DOMAIN/healthz" 2>/dev/null; then
  echo "https://$DOMAIN/healthz doesn't answer yet. Point the pages there once the site is live (LAUNCH.md)."; exit 1
fi
DOCS="$(cd "$(dirname "$0")/.." && pwd)/docs"

page() {  # file, path on the site, title
  local url="https://$DOMAIN$2"
  cat > "$DOCS/$1" <<EOF
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$3</title>
<link rel="canonical" href="$url">
<meta http-equiv="refresh" content="0; url=$url">
<meta name="robots" content="noindex">
<style>
:root{--bg:#F6F7FB;--ink:#14161F;--link:#3730A3}
@media (prefers-color-scheme:dark){:root{--bg:#0E1018;--ink:#E8EAF2;--link:#A5B4FC}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:560px;margin:0 auto;padding:64px 16px}
a{color:var(--link)}
</style>
</head>
<body>
<main>
<h1>$3 has moved</h1>
<p>It's now at <a href="$url">$url</a>. Taking you there…</p>
</main>
<script>location.replace("$url" + location.hash);</script>
</body>
</html>
EOF
  echo "  docs/$1 -> $url"
}

page index.html /welcome "Pit Crew"
page privacy.html /privacy "Pit Crew Privacy Policy"
page terms.html /terms "Pit Crew Terms of Service"
echo "Done. Commit docs/ on your branch (git add docs && git commit -m \"Point the old pages at $DOMAIN\") and open a PR."
