"""数据目录（home / rpa/state / runs）的解析与显式迁移。

解析只计算路径、不创建目录、不接触任何现有会话；迁移由调用者显式指定
源与目标，见 :func:`migrate_data`。
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_HOME = "MISONG_HOME"
APP_DIR = "misong"


class MigrationError(RuntimeError):
    """迁移前置校验失败；不产生任何写入。"""


@dataclass(frozen=True)
class Paths:
    """resolve_paths 的解析结果；字段均为绝对 Path。"""

    home: Path
    state: Path
    runs: Path


def _is_link(path: Path) -> bool:
    """符号链接，以及 Windows 上 is_symlink 不识别的目录联接（junction）。"""
    if path.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            stat = os.stat(path, follow_symlinks=False)
        except OSError:
            return False
        return getattr(stat, "st_reparse_tag", 0) != 0
    return False


def _same_file(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as fa, second.open("rb") as fb:
        while chunk := fa.read(1 << 20):
            if chunk != fb.read(1 << 20):
                return False
    return True


def _validate_ancestors(path: Path) -> None:
    for ancestor in (path.absolute(), *path.absolute().parents):
        if _is_link(ancestor):
            raise MigrationError("迁移路径不能经过符号链接或目录联接")
        if ancestor.exists() and not ancestor.is_dir():
            raise MigrationError("迁移目录或其父目录已被文件占用")


def _source_root() -> Path | None:
    """返回源码 checkout 的仓库根；普通（非 editable）安装返回 None。"""
    root = Path(__file__).resolve().parents[2]
    if (root / "src" / "misong" / "paths.py").is_file():
        return root
    return None


def _default_home(env) -> Path:
    if sys.platform == "win32":
        base = str(env.get("LOCALAPPDATA", "")).strip()
        if base:
            return Path(base) / APP_DIR
        return Path.home() / "AppData" / "Local" / APP_DIR
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR
    base = str(env.get("XDG_DATA_HOME", "")).strip()
    if base:
        return Path(base).expanduser() / APP_DIR
    return Path.home() / ".local" / "share" / APP_DIR


def resolve_paths(env=None) -> Paths:
    """按 MISONG_HOME > 源码 checkout > 平台用户数据目录 的优先级解析数据目录。

    显式设置 ``MISONG_HOME`` 时 ``state``/``runs`` 分别为 ``<home>/rpa/state``
    与 ``<home>/runs``；源码 checkout 未设置环境变量时沿用仓库内原目录；
    普通安装默认 Windows ``%LOCALAPPDATA%/misong``，macOS 与 Linux 使用各自
    的用户数据目录约定。空白的环境变量值视为未设置。
    """
    env = os.environ if env is None else env
    raw = str(env.get(ENV_HOME, "")).strip()
    if raw:
        home = Path(raw).expanduser().resolve()
    elif (root := _source_root()) is not None:
        home = root
    else:
        home = _default_home(env).resolve()
    return Paths(home=home, state=home / "rpa" / "state", runs=home / "runs")


def migrate_data(source, destination) -> None:
    """把调用者显式指定的旧数据目录完整复制到新目录；原数据保持不动。

    全部校验（缺失、符号链接、目录联接、目标占用与内容冲突）在任何写入之前
    完成：目标已有相同内容时跳过，存在不同内容时整体拒绝，保证可安全重跑。
    不自动推断源或目标；接线与时机由调用方决定。
    """
    src_raw, dst_raw = Path(source).expanduser(), Path(destination).expanduser()
    _validate_ancestors(src_raw)
    _validate_ancestors(dst_raw)
    if _is_link(src_raw):
        raise MigrationError(f"源目录不能是符号链接或联接点：{src_raw}")
    if not src_raw.is_dir():
        raise MigrationError(f"源目录不存在或不是目录：{src_raw}")
    if _is_link(dst_raw):
        raise MigrationError(f"目标目录不能是符号链接或联接点：{dst_raw}")
    if dst_raw.exists() and not dst_raw.is_dir():
        raise MigrationError(f"目标路径已被文件占用：{dst_raw}")
    src, dst = src_raw.resolve(), dst_raw.resolve()
    if dst == src or dst.is_relative_to(src):
        raise MigrationError(f"目标目录不能位于源目录内：{dst}")

    def unreadable_directory(error):
        raise MigrationError("无法完整读取源目录，迁移已停止；请检查权限或文件占用") from error

    copies, directories = [], set()
    for root, dir_names, file_names in os.walk(src, followlinks=False, onerror=unreadable_directory):
        here = Path(root)
        target = dst / here.relative_to(src)
        _validate_ancestors(target)
        for name in (*dir_names, *file_names):
            if _is_link(here / name):
                raise MigrationError(f"拒绝迁移符号链接或联接点：{here / name}")
        for name in dir_names:
            _validate_ancestors(target / name)
            directories.add(target / name)
        for name in file_names:
            origin, copy = here / name, target / name
            if _is_link(copy):
                raise MigrationError("目标已有符号链接或目录联接，拒绝覆盖")
            if copy.is_dir():
                raise MigrationError(f"目标已有同名目录，无法复制文件：{copy}")
            if copy.exists() and not _same_file(origin, copy):
                raise MigrationError(f"目标已存在不同内容，拒绝覆盖：{copy}")
            if not copy.exists():
                copies.append((origin, copy))

    for directory in (dst, *directories):
        directory.mkdir(parents=True, exist_ok=True)
    for origin, copy in copies:
        shutil.copy2(origin, copy)
