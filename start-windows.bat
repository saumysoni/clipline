@echo off
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting things up. This takes a few minutes...
  py -3 -m venv .venv
)
rem (Re)install add-ons on the first run, and again whenever requirements.txt changes.
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>&1
if errorlevel 1 (
  echo Installing / updating Cliplines add-ons...
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install --upgrade -r requirements.txt && copy /y requirements.txt .venv\installed-requirements.txt >nul
)
.venv\Scripts\python app.py
pause
