"""
Paths shared by every part of Pit Crew. Each can be changed with an environment setting, so a cloud
server (or a test) can point them somewhere else without touching the code.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent                          # the app's folder (named clipline)
JOBS_DIR = Path(os.getenv("JOBS_DIR") or ROOT / "jobs")         # everything Pit Crew makes, one folder per vlog
