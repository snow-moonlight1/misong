"""MP4 opening-box embedding and legacy concatenation compatibility.

New cover layers use streaming free-box embedding, co64 and ZIP64 relocation
from mp4.py. concat_merge remains available for old CLI workflows; archive
scanners have bounded prefix search windows, so large leading videos should
use embed_in_mp4 instead. unwrap handles both layouts and numbered volumes.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import struct
import tempfile
import time
from pathlib import Path

from . import formats
from .mp4 import embed_in_mp4, extract_embedded, embedded_payload, relocate_zip

ZIP_LOCAL = b"PK\x03\x04"
ZIP_CENTRAL = b"PK\x01\x02"
ZIP_EOCD = b"PK\x05\x06"
ZIP64_EOCD = b"PK\x06\x07"

SIGNATURES: list[tuple[bytes, str]] = [
    (ZIP_LOCAL, "zip"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07\x00\x00", "rar4"),
    (b"Rar!\x1a\x07\x01\x00", "rar5"),
    (b"\x1f\x8b", "gz"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"BZh", "bz2"),
    (b"\x28\xb5\x2f\xfd", "zst"),
    (b"\x04\x22\x4d\x18", "lz4"),
]

MAX_SIG_LEN = max(len(s) for s, _ in SIGNATURES)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def iter_signature_hits(path: Path):
    """Yield (offset, fmt_key) for archive magic bytes found in path."""
    buf_size = 8 * 1024 * 1024
    with path.open("rb") as fh:
        base = 0  # file offset of window start
        carry = b""
        while True:
            blk = fh.read(buf_size)
            if not blk:
                break
            window = carry + blk
            win_start = base - len(carry)
            for sig, fmt in SIGNATURES:
                start = 0
                while True:
                    i = window.find(sig, start)
                    if i < 0:
                        break
                    yield win_start + i, fmt
                    start = i + 1
            carry = window[-(MAX_SIG_LEN - 1):]
            base += len(blk)


# ---------------------------------------------------------------- zip offset fix
def _eocd_of(data: bytes) -> int:
    idx = data.rfind(ZIP_EOCD)
    if idx < 0:
        raise ValueError("不是标准 zip（找不到 EOCD）")
    return idx


def _fix_zip_offsets(data: bytes, delta: int) -> bytes:
    """Rewrite all absolute offsets in a standalone zip by +delta."""
    src, dst = io.BytesIO(data), io.BytesIO()
    relocate_zip(src, dst, delta)
    return dst.getvalue()



def _zip_needs_fix(data: bytes) -> bool:
    """True when the zip is standalone (first local header at offset 0) and
    therefore its offsets must be shifted after we prepend bytes."""
    try:
        eocd = _eocd_of(data)
        cd_off = struct.unpack_from("<I", data, eocd + 16)[0]
        if data[cd_off:cd_off + 4] != ZIP_CENTRAL:
            return False
        lo = struct.unpack_from("<I", data, cd_off + 42)[0]
        return lo == 0
    except ValueError:
        return False


def concat_merge(files: list[Path], out_path: Path, fix_zip: bool = True) -> dict:
    """copy /b equivalent, with optional zip offset patching (recommended on)."""
    files = [Path(f) for f in files]
    blobs = [f.read_bytes() for f in files]
    prepend = b"".join(blobs[:-1])
    tail = blobs[-1]
    report = {"mode": "concat-raw", "inputs": [str(f) for f in files]}

    if fix_zip and tail.startswith(ZIP_LOCAL) and _zip_needs_fix(tail):
        try:
            tail = _fix_zip_offsets(tail, len(prepend))
            report["mode"] = "concat-fixed-zip"
        except ValueError as e:
            report["zip_fix_skipped"] = str(e)

    blob = prepend + tail
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    report.update(out=str(out_path), size=len(blob), sha256=_sha(blob))
    return report


def split_at(path: Path, head_out: Path, tail_out: Path, offset: int) -> None:
    """Inverse of concat: cut one merged file into head/tail at a byte offset."""
    with Path(path).open("rb") as fh:
        head_data = fh.read(offset)
        tail_data = fh.read()
    Path(head_out).write_bytes(head_data)
    Path(tail_out).write_bytes(tail_data)


def unwrap(path: Path, out_dir: Path, password: str | None = None,
           only_format: str | None = None, keep_looking: bool = False,
           chain: list[str] | None = None) -> list[Path]:
    """Extract archive payloads embedded in a merged/disguised file.

    Scans magic signatures, tries extraction at each hit offset. With `chain`
    (list of passwords, outermost first) it keeps peeling sniffed layers the
    way a receiver would manually.
    """
    from . import split
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    current, found, archive_index = path, [], 0
    # Transforms (cover/split/rename) do not consume archive passwords in sniff
    # mode, since their existence cannot be known in advance without a manifest.
    for depth in range(100):
        step = out_dir / f"peel-{depth}"
        step.mkdir(exist_ok=True)
        if current.is_dir():
            children = list(current.iterdir())
            volumes = [p for p in children if split._PART_NAME_RE.match(p.name)]
            if volumes and len(volumes) == len(children):
                current = split.join(volumes[0], step / split.collect_parts(volumes[0])[0])
            else:
                break
        elif split._PART_NAME_RE.match(current.name):
            current = split.join(current, step / split.collect_parts(current)[0])
        try:
            embedded = embedded_payload(current) if current.is_file() else None
        except ValueError:
            embedded = None
        if embedded:
            current = extract_embedded(current, step / ("payload." + embedded[2]))
        fmt = formats.sniff(current)
        pwd = chain[archive_index] if chain is not None and archive_index < len(chain) else password
        if fmt and (not only_format or fmt == only_format):
            current = formats.extract(fmt, current, step, password=pwd)
            archive_index += 1
            found.append(current)
            if chain is None:
                return found
            continue
        # Legacy concatenations still use signature scanning, in bounded chunks.
        extracted = False
        if current.is_file():
            for off, fmt in iter_signature_hits(current):
                if off == 0 or (only_format and fmt != only_format) or fmt in ("rar4", "rar5"):
                    continue
                candidate = step / ("candidate." + fmt)
                with current.open("rb") as fi, candidate.open("wb") as fo:
                    fi.seek(off)
                    shutil.copyfileobj(fi, fo, 8 * 1024 * 1024)
                work = step / f"hit-{off}"
                work.mkdir(exist_ok=True)
                try:
                    res = formats.extract(fmt, candidate, work, password=pwd)
                except Exception:
                    candidate.unlink(missing_ok=True)
                    continue
                candidate.unlink(missing_ok=True)
                current, extracted = res, True
                archive_index += 1
                found.append(current)
                if chain is None and not keep_looking:
                    return found
                break
        if not extracted:
            break
    if not found:
        raise RuntimeError("未找到可解出的归档载荷，请检查所有分卷和密码")
    return found
