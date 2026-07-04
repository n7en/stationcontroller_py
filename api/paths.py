"""
Repo-anchored paths for the API layer.

main.py resolves all config paths relative to the repository root so the app
can be launched from any working directory; routers must do the same or they
would read and write different files than the app loaded at startup.
"""
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"
