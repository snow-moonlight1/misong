"""One-shot volume splitting / joining (netdisk-friendly).

Raw byte split with `.001` naming (plus legacy `.partNNN` support on join).
A sidecar json records sha256 of every part and the whole file so `join`
can verify integrity before reassembly — mirrors what RAR/7z volumes do,
but works with *any* artifact (including disguised .mp4/.lz4 ones).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .metadata import SPLIT_EXTS, find_sidecar

PART_SUFFIX = "."
SIDECAR_EXT = SPLIT_EXTS[0]

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgGtT]?)[iI]?[bB]?\s*$")
_UNITS = {"": 1024**2, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def parse_size(text: str) -> int:
    m = _SIZE_RE.match(text)
    if not m:
        raise ValueError(f"无法解析大小: {text}（示例: 4000M / 1G / 200mb）")
    num, unit = m.groups()
    # Explicit B remains available for byte-sized regression fixtures.
    multiplier = 1 if not unit and text.strip().lower().endswith("b") else _UNITS[unit.upper()]
    value = int(float(num) * multiplier)
    if value <= 0:
        raise ValueError("每卷大小必须大于 0")
    return value


def _sha256_file(p: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def split(src: Path, size: int, out_dir: Path | None = None,
          prefix: str | None = None, keep_name_ext: bool = True) -> dict:
    """Split src into parts. Returns sidecar manifest (also written to disk)."""
    src = Path(src)
    if size <= 0:
        raise ValueError("每卷大小必须大于 0")
    total = src.stat().st_size
    n = max(1, (total + size - 1) // size)
    base = prefix or src.name
    out_dir = Path(out_dir or src.parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    parts: list[dict] = []
    with src.open("rb") as fh:
        for i in range(n):
            part_path = out_dir / (f"{base}{PART_SUFFIX}{i + 1:03d}" if n > 1 else base)
            if part_path.resolve() == src.resolve():
                parts.append({"name": src.name, "index": 1, "size": total, "sha256": _sha256_file(src)})
                break
            remaining = size
            with part_path.open("wb") as fo:
                while remaining > 0:
                    blk = fh.read(min(remaining, 8 * 1024 * 1024))
                    if not blk:
                        break
                    fo.write(blk)
                    remaining -= len(blk)
            parts.append({
                "name": part_path.name,
                "index": i + 1,
                "size": part_path.stat().st_size,
                "sha256": _sha256_file(part_path),
            })

    manifest = {
        "version": 1,
        "source": src.name,
        "source_size": total,
        "source_sha256": _sha256_file(src),
        "part_size": size,
        "part_count": n,
        "parts": parts,
    }
    sidecar = out_dir / f"{base}{SIDECAR_EXT}"
    sidecar.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


_PART_NAME_RE = re.compile(r"^(?P<base>.+?)(?:\.part(?P<idx>\d{3,})|\.(?P<idx0>\d{3,}))$")
_CHECKSUM_RE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")


def _part_checksums(folder: Path, base: str) -> dict[str, str]:
    """Read sha256sum records for this volume set without following paths."""
    records: dict[str, str] = {}
    for checksum_file in sorted(folder.glob("*.sha256")):
        for line in checksum_file.read_text(encoding="utf-8-sig").splitlines():
            match = _CHECKSUM_RE.fullmatch(line)
            if not match:
                continue
            digest, name = match.groups()
            part = _PART_NAME_RE.fullmatch(name)
            if not part or part.group("base") != base or Path(name).name != name:
                continue
            digest = digest.lower()
            if name in records and records[name] != digest:
                raise RuntimeError(f"SHA-256 校验记录冲突: {name}")
            records[name] = digest
    return records


def has_verification(any_part: Path) -> bool:
    base, parts = collect_parts(any_part)
    folder = parts[0].parent
    return find_sidecar(folder / base, SPLIT_EXTS) is not None or bool(_part_checksums(folder, base))


def collect_parts(any_part: Path) -> tuple[str, list[Path]]:
    """Given one part file, find its siblings and return (base, ordered parts)."""
    any_part = Path(any_part)
    m = _PART_NAME_RE.match(any_part.name)
    if not m:
        raise ValueError(f"文件名不像分卷: {any_part.name}（期望 xxx.part001 或 xxx.001）")
    base = m.group("base")
    folder = any_part.parent
    cand: list[tuple[int, Path]] = []
    for p in folder.iterdir():
        mm = _PART_NAME_RE.match(p.name)
        if mm and mm.group("base") == base:
            idx = int(mm.group("idx") or mm.group("idx0"))
            cand.append((idx, p))
    if not cand:
        raise FileNotFoundError(f"在 {folder} 找不到 {base} 的分卷")
    cand.sort()
    idxs = [i for i, _ in cand]
    if idxs != list(range(1, len(idxs) + 1)):
        raise ValueError(f"分卷序号不连续: {idxs}")
    return base, [p for _, p in cand]


def join(any_part: Path, out_path: Path | None = None, verify: bool = True) -> Path:
    base, parts = collect_parts(any_part)
    folder = parts[0].parent
    out_path = Path(out_path or folder / base)
    if out_path.resolve() in {p.resolve() for p in parts}:
        raise ValueError("合并输出不能覆盖分卷")

    sidecar = find_sidecar(folder / base, SPLIT_EXTS)
    expected = None
    if sidecar is not None:
        expected = json.loads(sidecar.read_text(encoding="utf-8"))
    if expected and verify:
        if len(parts) != expected["part_count"]:
            raise RuntimeError("分卷校验失败：缺少分卷")
        for p, rec in zip(parts, expected["parts"]):
            if p.name != rec["name"] or p.stat().st_size != rec["size"] or rec["sha256"] != _sha256_file(p):
                raise RuntimeError(f"分卷校验失败: {p.name}（请重新下载该卷）")

    if verify:
        checksums = _part_checksums(folder, base)
        if checksums:
            missing = checksums.keys() - {p.name for p in parts}
            if missing:
                raise RuntimeError("分卷校验失败：缺少分卷 " + ", ".join(sorted(missing)))
            for p in parts:
                if p.name not in checksums:
                    raise RuntimeError(f"缺少 SHA-256 校验记录: {p.name}")
                if _sha256_file(p) != checksums[p.name]:
                    raise RuntimeError(f"分卷校验失败: {p.name}（请重新下载该卷）")

    h = hashlib.sha256()
    with out_path.open("wb") as fo:
        for i, p in enumerate(parts):
            with p.open("rb") as fh:
                for blk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
                    fo.write(blk)
                    h.update(blk)

    if expected and verify:
        if h.hexdigest() != expected["source_sha256"]:
            out_path.unlink(missing_ok=True)
            raise RuntimeError("整体 sha256 与清单不符，产物已删除")
    return out_path
