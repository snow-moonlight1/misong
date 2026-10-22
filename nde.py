"""Repo-root launcher: python nde.py <cmd> ... (no install needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from nde.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
