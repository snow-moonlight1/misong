"""Durable local job records. Never store archive passwords here."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path


def save_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(6):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                # Windows readers (including task-center polling) briefly deny
                # replacement while their handle is open. Keep the old record
                # intact and retry the same fully flushed temporary file.
                if os.name != "nt" or attempt == 5:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        Path(temp).unlink(missing_ok=True)


def fingerprint(path: Path) -> dict:
    path = Path(path).resolve()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return {"path": str(path), "size": path.stat().st_size, "sha256": h.hexdigest()}


def verify_files(files: list[dict]) -> None:
    for rec in files:
        if fingerprint(Path(rec["path"])) != {k: rec[k] for k in ("path", "size", "sha256")}:
            raise ValueError(f"文件已改变，请创建新任务：{rec['path']}")


@contextlib.contextmanager
def exclusive(path: Path):
    """OS lock is released even on process crashes; lock file is not a PID flag."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise RuntimeError(f"任务或账号正在使用中：{path.name}") from e
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
