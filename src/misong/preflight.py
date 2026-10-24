"""Conservative peak-space and I/O estimates, independent of layer count."""
from __future__ import annotations

import os
import shutil
import string
from pathlib import Path

from .layers import validate

GB = 1024**3


def disk_roots(target):
    if os.name == "nt":
        import ctypes
        return [Path(c + ":/") for c in string.ascii_uppercase
                if ctypes.windll.kernel32.GetDriveTypeW(c + ":\\") == 3]
    return [Path(target).anchor or "/"]


def _existing_parent(path):
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    return path


def estimate(inputs, layers, out, *, keep_layers=False):
    paths = [Path(p).resolve(strict=True) for p in inputs]
    validate(layers, paths)
    source = sum(p.stat().st_size if p.is_file() else
                 sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) for p in paths)
    current, peak, io, retained = source, 0, 0, 0
    for layer in layers:
        next_size = current
        if layer.type == "archive":
            next_size = int(current * 1.01) + 1024**2  # incompressible input + archive metadata
        elif layer.type == "cover":
            next_size += Path(layer.video).stat().st_size + 1024**2
        # ZIP covers also require a streaming relocation scratch archive.
        scratch = current if layer.type == "cover" else 0
        peak = max(peak, current + next_size + scratch + retained)
        io += current + next_size * 2  # transform, hashes, and final metadata checks
        if keep_layers:
            retained += next_size
        current = next_size
    # Grouping several inputs can fall back from hard links to copies.
    peak += source if len(paths) > 1 else 0
    required = int(peak * 1.05) + 64 * 1024**2
    target = Path(out).resolve()
    available = shutil.disk_usage(_existing_parent(target)).free
    selected = target
    largest = available
    if available < required:
        best = None
        for root in disk_roots(target):
            try:
                free = shutil.disk_usage(root).free
            except OSError:
                continue
            if free > largest:
                largest, best = free, Path(root)
        if best and largest >= required:
            selected = best / "misong-runs" / target.name
    ok = largest >= required
    minutes = max(0.1, io / (150 * 1024**2) / 60)
    message = f"本次约需中间空间 {required / GB:.2f} GB，总读写约 {io / GB:.2f} GB，预计约 {minutes:.1f} 分钟"
    if not ok:
        message = f"需要约 {required / GB:.2f} GB，当前最大可用盘仅 {largest / GB:.2f} GB，请减少层数或更换位置。" + message
    elif selected != target:
        message += f"；目标盘空间不足，自动改放 {selected}"
    return {"ok": ok, "required_bytes": required, "io_bytes": io, "minutes": minutes,
            "available_bytes": largest, "out": str(selected), "message": message,
            "relocated": selected != target}


def require(inputs, layers, out, notify=print, *, keep_layers=False):
    result = estimate(inputs, layers, out, keep_layers=keep_layers)
    notify(result["message"])
    if not result["ok"]:
        raise ValueError(result["message"])
    return Path(result["out"])
