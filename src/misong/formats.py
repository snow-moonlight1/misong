"""Format registry: every layer format knows how to compress and extract itself.

Two families:
- "raw": stream compressors that turn exactly one file into one blob
  (lz4, zst, br, gz, ...). Directories must be tarred first or wrapped.
- "container": archive formats that hold many files/dirs (7z, zip, tar.*)

Password support: only 7z (AES-256, optional header encryption) and zip
(AES via pyzipper). For raw formats the pack pipeline automatically adds an
inner 7z layer when a password is requested.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import brotli
import lz4.frame
import py7zr
import pyzipper
import zstandard as zstd

ZSTD_LEVEL = 19
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def sevenzip_executable() -> Path | None:
    """Prefer the unmodified bundled executable, then an installed copy."""
    vendor = Path(__file__).parent / "vendor" / "7zip"
    for name in ("7za.exe", "7z.exe"):
        candidate = vendor / name
        if candidate.is_file() and (name == "7za.exe" or (vendor / "7z.dll").is_file()):
            return candidate
    for name in ("7zz", "7z", "7za"):
        if found := shutil.which(name):
            return Path(found)
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root and (candidate := Path(root) / "7-Zip" / "7z.exe").is_file():
            return candidate
    return None


def _sevenzip(args: list[str], *, cwd: Path | None = None) -> bool:
    executable = sevenzip_executable()
    if not executable:
        return False
    try:
        result = subprocess.run([str(executable), *args], cwd=cwd, stdin=subprocess.DEVNULL,
                                capture_output=True, creationflags=NO_WINDOW)
    except OSError:
        return False  # an unavailable binary must not disable the Python backend
    if result.returncode:
        # Never echo the command or tool output: they may contain a password.
        raise RuntimeError(f"7-Zip 操作失败（代码 {result.returncode}），请检查密码、文件和剩余空间")
    return True


@dataclass
class Format:
    key: str
    kind: str  # raw | container
    native_exts: tuple[str, ...]
    supports_password: bool = False
    accepts_dir: bool = True
    note: str = ""

    def is_final_ext_ok(self, ext: str) -> bool:
        return ext.lower() in self.native_exts


def _stream_compress(mod, src: Path, dst: Path) -> None:
    with src.open("rb") as fi, mod.open(dst, "wb") as fo:
        shutil.copyfileobj(fi, fo, 1024 * 1024)


def _stream_extract(mod, src: Path, dst: Path) -> None:
    with mod.open(src, "rb") as fi, dst.open("wb") as fo:
        shutil.copyfileobj(fi, fo, 1024 * 1024)


def _compress_7z(src: Path, dst: Path, password: str | None, header_enc: bool, level=None) -> None:
    with py7zr.SevenZipFile(
        dst, "w", password=password,
        header_encryption=bool(password) and header_enc,
        filters=[{"id": py7zr.FILTER_COPY}] if level == 0 else None
    ) as z:
        if src.is_dir():
            z.writeall(src, arcname=src.name)
        else:
            z.write(src, arcname=src.name)


def _extract_7z(src: Path, dst_dir: Path, password: str | None) -> list[Path]:
    out = dst_dir / "extracted"
    out.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(src, "r", password=password) as z:
        names = z.getnames()
        z.extractall(path=out)
    tops = [out / n.split("/")[0] for n in {n.split("/")[0] for n in names}]
    return [p for p in tops if p.exists()]


def _compress_zip(src: Path, dst: Path, password: str | None, level=None) -> None:
    import zipfile
    if password:
        zf: zipfile.ZipFile = pyzipper.AESZipFile(
            dst, "w", compression=zipfile.ZIP_STORED if level == 0 else zipfile.ZIP_DEFLATED)
        zf.setencryption(pyzipper.WZ_AES, nbits=256)
        zf.setpassword(password.encode("utf-8"))
    else:
        zf = zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED if level == 0 else zipfile.ZIP_DEFLATED)
    with zf:
        if src.is_dir():
            for p in sorted(src.rglob("*")):
                arc = Path(src.name) / p.relative_to(src)
                if p.is_file():
                    zf.write(p, arc)
        else:
            zf.write(src, src.name)


def _extract_zip(src: Path, dst_dir: Path, password: str | None) -> list[Path]:
    out = dst_dir / "extracted"
    out.mkdir(parents=True, exist_ok=True)
    pwd = password.encode("utf-8") if password else None
    with pyzipper.AESZipFile(src, "r") as zf:
        names = zf.namelist()
        zf.extractall(out, pwd=pwd)
    tops = [out / n.split("/")[0] for n in {n.split("/")[0] for n in names if not n.startswith("/")} if n.split("/")[0]]
    return [p for p in tops if p.exists()]


def _compress_tar(src: Path, dst: Path, mode: str) -> None:
    with tarfile.open(dst, f"w:{mode}") as tf:
        tf.add(src, arcname=src.name)


def _extract_tar(src: Path, dst_dir: Path, mode: str) -> list[Path]:
    out = dst_dir / "extracted"
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src, "r:*") as tf:
        members = [m.name.split("/")[0] for m in tf.getmembers()]
        tf.extractall(out, filter="data")
    # Windows-created tars carry 0o666/0o777 modes; the data filter chmods
    # them to 0o600/0o700 which can lock freshly created dirs mid-pipeline.
    for p in out.rglob("*"):
        try:
            os.chmod(p, 0o755 if p.is_dir() else 0o644)
        except OSError:
            pass
    tops = sorted({out / m for m in members if m})
    return [p for p in tops if p.exists()]


def _compress_zstd(src: Path, dst: Path) -> None:
    cctx = zstd.ZstdCompressor(level=ZSTD_LEVEL)
    with src.open("rb") as fi, dst.open("wb") as fo:
        with cctx.stream_reader(fi) as reader, fo:
            shutil.copyfileobj(reader, fo, 1024 * 1024)


def _extract_zstd(src: Path, dst: Path) -> None:
    dctx = zstd.ZstdDecompressor()
    with src.open("rb") as fi, dst.open("wb") as fo:
        with dctx.stream_reader(fi) as reader:
            shutil.copyfileobj(reader, fo, 1024 * 1024)


def _compress_brotli(src: Path, dst: Path) -> None:
    data = src.read_bytes()
    dst.write_bytes(brotli.compress(data, quality=11))


def _extract_brotli(src: Path, dst: Path) -> None:
    dst.write_bytes(brotli.decompress(src.read_bytes()))


def _compress_lzma_raw(src: Path, dst: Path) -> None:
    _stream_compress(lzma, src, dst)


FORMATS: dict[str, Format] = {
    # containers
    "7z": Format("7z", "container", (".7z", ".lzma", ".zip", ".rar", ".001"), True, True,
                "AES-256；可选头加密(文件名也不可见)；网盘在线解压无法处理"),
    "zip": Format("zip", "container", (".zip", ".mp4", ".png"), True, True,
                  "AES(AE-2)加密；改后缀 .zip 后 WinRAR/7-Zip 可直接识别尾部 EOCD"),
    "tar.gz": Format("tar.gz", "container", (".tar.gz", ".tgz", ".mp4", ".zip"), False, True),
    "tar.bz2": Format("tar.bz2", "container", (".tar.bz2", ".tbz2", ".mp4", ".zip"), False, True),
    "tar.xz": Format("tar.xz", "container", (".tar.xz", ".txz", ".mp4", ".zip"), False, True),
    "tar": Format("tar", "container", (".tar", ".mp4", ".zip"), False, True),
    # raw single-stream (冷门)
    "lz4": Format("lz4", "raw", (".lz4", ".mp4", ".zip"), False, False,
                  "lz4 帧格式；资源圈常把 .7z 改名 .lz4 骗过后缀审查"),
    "zst": Format("zst", "raw", (".zst", ".lz4", ".mp4"), False, False, "zstd level 19"),
    "br": Format("br", "raw", (".br", ".zst", ".mp4"), False, False, "brotli quality 11"),
    "gz": Format("gz", "raw", (".gz", ".lz4", ".mp4"), False, False),
    "bz2": Format("bz2", "raw", (".bz2", ".lz4", ".mp4"), False, False),
    "xz": Format("xz", "raw", (".xz", ".lz4", ".mp4"), False, False),
    "lzma": Format("lzma", "raw", (".lzma", ".xz", ".mp4"), False, False),
}

ORDER = ["7z", "zip", "tar.gz", "tar.bz2", "tar.xz", "tar",
         "lz4", "zst", "br", "gz", "bz2", "xz", "lzma"]


def get(fmt: str) -> Format:
    key = fmt.lower().lstrip(".")
    if key in ("tgz",):
        key = "tar.gz"
    if key in ("tbz2", "tbz"):
        key = "tar.bz2"
    if key in ("txz",):
        key = "tar.xz"
    if key not in FORMATS:
        raise KeyError(f"unknown format '{fmt}'; known: {', '.join(ORDER)}")
    return FORMATS[key]


def compress(fmt_key: str, src: Path, dst: Path, password: str | None = None,
             header_enc: bool = False, level: int | None = None) -> tuple[str, bool]:
    """Compress src (file or dir) into dst.

    Returns (format_key, tar_prepended). raw formats on a directory input are
    transparently wrapped in an uncompressed tar first (netdisk chains often
    look exactly like this: tar -> lz4 -> 7z).
    """
    f = get(fmt_key)
    src, dst = Path(src).resolve(), Path(dst).resolve()
    if level is not None and not 0 <= level <= 9:
        raise ValueError("压缩等级应为 0–9")
    if f.key in ("7z", "zip"):
        args = ["a", f"-t{f.key}", "-y", "-bd", "-mmt=on", f"-mx={5 if level is None else level}"]
        if password:
            args += ["-p" + password, "-mhe=on" if f.key == "7z" and header_enc else
                     ("-mem=AES256" if f.key == "zip" else "-mhe=off")]
        if _sevenzip([*args, str(dst), "--", src.name], cwd=src.parent):
            return f.key, False
    tar_pre = False
    if f.kind == "container":
        if f.key == "7z":
            _compress_7z(src, dst, password, header_enc, level)
        elif f.key == "zip":
            _compress_zip(src, dst, password, level)
        else:
            if password:
                raise ValueError(f"{f.key} 不支持密码；请改用 7z/zip 层承载密码")
            _compress_tar(src, dst, f.key.partition(".")[2])
    else:
        if src.is_dir():
            tar_pre = True
            tmp_tar = dst.with_name(dst.stem + ".inner.tar")
            _compress_tar(src, tmp_tar, "")
            src = tmp_tar
        if f.key == "zst":
            _compress_zstd(src, dst)
        elif f.key == "br":
            _compress_brotli(src, dst)
        elif f.key == "lz4":
            with lz4.frame.open(dst, "wb") as fo, src.open("rb") as fi:
                shutil.copyfileobj(fi, fo, 1024 * 1024)
        elif f.key == "gz":
            _stream_compress(gzip, src, dst)
        elif f.key == "bz2":
            _stream_compress(bz2, src, dst)
        elif f.key == "xz":
            _stream_compress(lzma, src, dst)
        elif f.key == "lzma":
            with lzma.LZMAFile(dst, "wb", format=lzma.FORMAT_ALONE) as fo, src.open("rb") as fi:
                shutil.copyfileobj(fi, fo, 1024 * 1024)
        if tar_pre:
            (dst.with_name(dst.stem + ".inner.tar")).unlink(missing_ok=True)
    return f.key, tar_pre


def extract(fmt_key: str, src: Path, workdir: Path, password: str | None = None) -> Path:
    """Extract src into workdir, return the single top-level result path.

    raw formats produce one decompressed file; containers produce the top-level
    dir/file inside <workdir>/extracted.
    """
    f = get(fmt_key)
    if f.kind == "container":
        if f.key in ("7z", "zip"):
            out = Path(workdir).resolve() / "extracted"
            out.mkdir(parents=True, exist_ok=True)
            if _sevenzip(["x", "-y", "-bd", "-p" + (password or "__MISONG_NO_PASSWORD__"),
                          "-o" + str(out), "--", str(Path(src).resolve())]):
                tops = list(out.iterdir())
                if len(tops) != 1:
                    raise RuntimeError(f"预期 1 个顶层条目，实际 {len(tops)}")
                return tops[0]
        if f.key == "7z":
            tops = _extract_7z(src, workdir, password)
        elif f.key == "zip":
            tops = _extract_zip(src, workdir, password)
        else:
            tops = _extract_tar(src, workdir, f.key.partition(".")[2])
        if len(tops) != 1:
            raise RuntimeError(f"预期 1 个顶层条目，实际 {len(tops)}：{[t.name for t in tops]}")
        return tops[0]
    out = workdir / (src.stem + ".bin")
    if f.key == "zst":
        _extract_zstd(src, out)
    elif f.key == "br":
        _extract_brotli(src, out)
    elif f.key == "lz4":
        with lz4.frame.open(src, "rb") as fi, out.open("wb") as fo:
            shutil.copyfileobj(fi, fo, 1024 * 1024)
    elif f.key == "gz":
        _stream_extract(gzip, src, out)
    elif f.key == "bz2":
        _stream_extract(bz2, src, out)
    elif f.key == "xz":
        _stream_extract(lzma, src, out)
    elif f.key == "lzma":
        with lzma.LZMAFile(src, "rb", format=lzma.FORMAT_ALONE) as fi, out.open("wb") as fo:
            shutil.copyfileobj(fi, fo, 1024 * 1024)
    return out


def extract_tar(src: Path, workdir: Path) -> Path:
    """Plain tar extraction (used to peel auto-prepended tars)."""
    tops = _extract_tar(src, workdir, "")
    if len(tops) != 1:
        raise RuntimeError(f"tar 层预期 1 个顶层条目，实际 {len(tops)}")
    return tops[0]


def sniff(src: Path) -> str | None:
    """Best-effort format detection by magic bytes (for unwrap)."""
    if not src.is_file():
        return None
    with src.open("rb") as fh:
        head = fh.read(16)
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"\x1f\x8b"):
        return "gz"
    if head.startswith(b"BZh"):
        return "bz2"
    if head.startswith(b"\xfd7zXZ"):
        return "xz"
    if head.startswith(b"\x5d\x00\x00"):
        return "lzma"
    if head[:4] in (b"\x04\x22\x4d\x18", b"\x22\x4d\x18\x04"):
        return "lz4"
    if head.startswith(b"\x28\xb5\x2f\xfd"):
        return "zst"
    # tar: "ustar" at offset 257
    if src.stat().st_size > 262:
        with src.open("rb") as fh:
            fh.seek(257)
            if fh.read(5) == b"ustar":
                return "tar"
    return None
