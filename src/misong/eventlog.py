"""Rotating structural events. Never persist arbitrary messages or requests."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

_LOCK = Lock()
_KINDS = {"pipeline", "pack", "upload", "restore", "text-delivery", "text-restore", "account"}
_STATES = {"running", "done", "paused", "error"}


class _Handler(RotatingFileHandler):
    def handleError(self, record):
        pass  # Logging failures must not expose local paths or interrupt work.


def record_job(state_dir: Path, *, kind: str, state: str) -> None:
    if kind not in _KINDS or state not in _STATES:
        return
    try:
        folder = Path(state_dir) / "logs"
        with _LOCK:
            folder.mkdir(parents=True, exist_ok=True)
            handler = _Handler(folder / "events.jsonl", maxBytes=512 * 1024,
                               backupCount=3, encoding="utf-8")
            try:
                message = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": "job",
                                      "kind": kind, "state": state}, ensure_ascii=True)
                handler.handle(logging.LogRecord("misong.events", logging.INFO, "", 0, message, (), None))
            finally:
                handler.close()
    except OSError:
        pass


def recent(state_dir: Path) -> list[str]:
    path = Path(state_dir) / "logs" / "events.jsonl"
    try:
        if path.is_symlink() or path.stat().st_size > 512 * 1024:
            return []
        return path.read_text(encoding="utf-8").splitlines()[-500:]
    except (OSError, UnicodeError):
        return []
