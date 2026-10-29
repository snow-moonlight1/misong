"""Restore an artifact and portable key using the existing inverse layer engine."""
from __future__ import annotations

import tempfile
from pathlib import Path

from . import pack, restore_key


def restore(source: Path, out: Path, key_file: Path | None = None, *, notify=print,
            check_cancel=lambda: None) -> dict:
    source, out = Path(source).resolve(strict=True), Path(out).resolve()
    base = source if source.is_dir() else source.parent
    if key_file is None:
        keys = [p for p in base.iterdir() if p.is_file() and p.suffix.lower() == restore_key.EXT]
        if len(keys) != 1:
            raise ValueError("请选择对应的 .mskey 还原钥匙" if not keys else "目录中有多把还原钥匙，请明确选择")
        key_file = keys[0]
    key_file = Path(key_file).resolve(strict=True)
    payload = restore_key.read(key_file)
    mf = payload["manifest"]
    records = mf["artifacts"]
    if source == key_file:
        raise ValueError("请同时选择压缩包或下载文件夹")
    if out == source or source.is_file() and out in source.parents:
        raise ValueError("还原目录不能覆盖输入资源")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("还原目录必须为空，避免覆盖已有文件")
    paths = [base / rec["name"] for rec in records]
    if len(records) == 1 and source.is_file():
        paths = [source]  # A renamed single artifact is identified by its hash.
    elif source.is_file() and source.name not in {rec["name"] for rec in records}:
        raise ValueError("所选文件与还原钥匙不匹配")
    missing = [rec["name"] for path, rec in zip(paths, records) if not path.is_file()]
    if missing:
        raise ValueError("缺少分卷或产物：" + "、".join(missing[:12]) + (" 等" if len(missing) > 12 else ""))
    notify(f"校验：正在核对 {len(paths)} 个产物与还原钥匙")
    for path, rec in zip(paths, records):
        check_cancel()
        if path.is_symlink() or path.resolve().parent != base.resolve() or path == key_file:
            raise ValueError("还原输入必须是同一目录中的普通文件")
        if path.stat().st_size != rec["size"] or pack._sha256(path) != rec["sha256"]:
            raise ValueError(f"校验不符：{rec['name']}，文件已损坏或还原钥匙不匹配")
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = {"number": 0, "format": ""}

    def progress(number, rec):
        check_cancel()
        stage.update(number=number, format=rec.get("format", rec["type"]))
        notify(f"还原：第 {number}/{len(mf['layers'])} 层（{stage['format']}）")

    with tempfile.TemporaryDirectory(prefix=".misong-restore-", dir=out.parent) as td:
        work = Path(td)
        try:
            result = pack.unest(paths[0], work / "output", payload["passwords"], manifest=mf, progress=progress)
        except Exception as error:
            check_cancel()
            # Exceptions from extractors must not echo passwords or command lines.
            if isinstance(error, ValueError) and str(error).startswith(("缺少分卷", "分卷校验失败")):
                raise
            raise ValueError(f"第 {stage['number']} 层（{stage['format']}）还原失败：请检查密码、文件完整性及可用空间") from None
        check_cancel()
        output = work / "output"
        if any(p.is_symlink() for p in output.rglob("*")):
            raise ValueError("还原结果含符号链接，已停止输出")
        # Publish only after the entire chain succeeds, leaving partial work private.
        if out.exists():
            if not out.is_dir() or any(out.iterdir()):
                raise ValueError("还原目录已被其他程序使用，请选择空目录")
            out.rmdir()
        output.rename(out)
        files = [{"name": p.name, "path": str(out / p.name)} for p in result]
    notify("完成：全部层已还原")
    return {"out": str(out), "files": files, "layers": len(mf["layers"]), "verified": True}
