#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: setting things up. This takes a few minutes..."
  python3 -m venv .venv
fi
# (Re)install add-ons on the first run, and again whenever requirements.txt changes.
if ! cmp -s requirements.txt .venv/installed-requirements.txt; then
  echo "Installing / updating Clipline's add-ons..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install --upgrade -r requirements.txt && cp requirements.txt .venv/installed-requirements.txt
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "FFmpeg isn't installed. In Terminal run:  brew install ffmpeg   then start Clipline again."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi
.venv/bin/python app.py
