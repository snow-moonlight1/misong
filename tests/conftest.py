"""Prefer the package over the repository's same-named CLI launcher."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
