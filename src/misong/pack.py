"""Build and reverse archive, cover, split and rename layers."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from . import formats, merge, split
from .layers import LayerSpec, migrate, output_ext, validate
from .metadata import MANIFEST_EXTS, find_sidecar


def default_output_for(src: Path, outer_fmt: str, disguise: str | None) -> Path:
    ext = disguise or formats.get(outer_fmt).native_exts[0]
    return src.with_name(src.name + "." + ext.lstrip("."))


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _stage_inputs(inputs, stage):
    """Group multiple roots using hard links where possible."""
    stage.mkdir()
    def link(src, dst):
        try:
            Path(dst).hardlink_to(src)
        except OSError:
            shutil.copy2(src, dst)
    for p in inputs:
        if p.is_dir():
            shutil.copytree(p, stage / p.name, copy_function=link)
        else:
            link(p, stage / p.name)
    return stage


def pack(inputs: list[Path], layers: list[LayerSpec], out_path: Path,
         keep_layers: bool = False) -> dict:
    inputs = [Path(p).resolve(strict=True) for p in inputs]
    if not inputs:
        raise ValueError("请先选择资源")
    if len({p.name.casefold() for p in inputs}) != len(inputs):
        raise ValueError("多个输入的文件名不能相同")
    layers = migrate(layers)
    validate(layers, inputs)
    out_path = Path(out_path).resolve()
    if any(out_path == p or p.is_dir() and p in out_path.parents for p in inputs):
        raise ValueError("输出不能覆盖输入或位于资源内部")
    if layers[-1].type != "archive" and not out_path.name.endswith(output_ext(layers)):
        out_path = out_path.with_suffix(output_ext(layers))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix=".misong-pack-", dir=out_path.parent) as td:
        tmp = Path(td)
        current = inputs
        previous_stage = None
        for i, ls in enumerate(layers):
            stage = tmp / f"step{i}"
            stage.mkdir()
            rec = {**ls.public(), "index": i, "input_names": [p.name for p in current]}
            if ls.type == "archive":
                src = current[0] if len(current) == 1 else _stage_inputs(current, stage / "bundle")
                fmt = formats.get(ls.fmt)
                nxt = stage / (f"layer{i}" + fmt.native_exts[0])
                level = ls.level if ls.level is not None else (None if i == 0 else 0)
                used, tar_pre = formats.compress(fmt.key, src, nxt, password=ls.password,
                                                header_enc=ls.header_enc, level=level)
                if src == stage / "bundle":
                    # Do not retain grouping hard links: otherwise deleting the
                    # previous volume stage would not release its disk blocks.
                    shutil.rmtree(src)
                rec.update(format=used, tar_pre=tar_pre, level=level)
                current = [nxt]
            elif ls.type == "cover":
                nxt = stage / f"layer{i}.mp4"
                rec.update(merge.embed_in_mp4(Path(ls.video), current[0], nxt, formats.sniff(current[0])))
                current = [nxt]
            elif ls.type == "rename":
                nxt = stage / (current[0].stem + "." + ls.ext.lstrip("."))
                shutil.copy2(current[0], nxt)
                current = [nxt]
            else:
                base = out_path.name if i == len(layers) - 1 else current[0].name
                sm = split.split(current[0], split.parse_size(str(ls.size)), stage, prefix=base)
                rec["split_manifest"] = sm
                current = [stage / p["name"] for p in sm["parts"]]
            rec["size"] = sum(p.stat().st_size for p in current)
            records.append(rec)
            if keep_layers:
                kd = out_path.with_name(out_path.name + ".layers") / f"L{i}"
                kd.mkdir(parents=True, exist_ok=True)
                for p in current:
                    shutil.copy2(p, kd / p.name)
            # Reclaim only intermediate files belonging to this invocation.
            if previous_stage:
                shutil.rmtree(previous_stage)
            previous_stage = stage
        artifacts = []
        for p in current:
            dest = out_path.parent / p.name if layers[-1].type == "split" else out_path
            shutil.move(str(p), dest)
            artifacts.append({"name": dest.name, "size": dest.stat().st_size, "sha256": _sha256(dest)})
        for side in stage.glob("*" + split.SIDECAR_EXT):
            shutil.move(str(side), out_path.parent / side.name)
    manifest = {"version": 2, "artifact": out_path.name, "artifacts": artifacts,
                "artifact_sha256": artifacts[0]["sha256"] if len(artifacts) == 1 else None,
                "layers": list(reversed(records))}  # outermost first, as in v1
    out_path.with_name(out_path.name + MANIFEST_EXTS[0]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def unest(artifact: Path, out_dir: Path, passwords: list[str | None],
          manifest: dict | None = None) -> list[Path]:
    artifact, out_dir = Path(artifact), Path(out_dir)
    mf = manifest
    if mf is None:
        base = artifact
        if split._PART_NAME_RE.match(artifact.name):
            base = artifact.with_name(split.collect_parts(artifact)[0])
        side = find_sidecar(base, MANIFEST_EXTS)
        if side is None:
            return merge.unwrap(artifact, out_dir, chain=passwords)
        mf = json.loads(side.read_text(encoding="utf-8"))
    if mf.get("version") not in (1, 2):
        raise ValueError("不支持的 .misong.json 清单版本")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".misong-unest-", dir=out_dir) as td:
        tmp, current = Path(td), artifact
        for i, rec in enumerate(mf["layers"]):
            step = tmp / f"u{i}"
            step.mkdir()
            kind = rec.get("type", "archive")
            names = rec.get("input_names", [])
            if kind == "split":
                sm = rec["split_manifest"]
                if current.is_dir():
                    current = current / sm["parts"][0]["name"]
                if not split._PART_NAME_RE.match(current.name) and _sha256(current) == sm["source_sha256"]:
                    # The receiver may already have run `misong join` manually.
                    continue
                if sm["part_count"] > 1:
                    actual = split.collect_parts(current)[1]
                    if len(actual) != sm["part_count"]:
                        raise ValueError("缺少分卷，请下载全部分卷")
                    for p, r in zip(actual, sm["parts"]):
                        if p.name != r["name"] or _sha256(p) != r["sha256"]:
                            raise RuntimeError(f"分卷校验失败: {p.name}")
                    current = split.join(current, step / sm["source"])
                else:
                    nxt = step / sm["source"]
                    shutil.copy2(current, nxt)
                    current = nxt
            elif kind == "cover":
                current = merge.extract_embedded(current, step / (names[0] if names else "payload.bin"))
            elif kind == "rename":
                nxt = step / names[0]
                shutil.copy2(current, nxt)
                current = nxt
            else:
                pwd = passwords[i] if i < len(passwords) else None
                if rec.get("password") and not pwd:
                    raise ValueError(f"第 {i + 1} 层({rec['format']})需要密码；非归档层用 - 占位")
                current = formats.extract(rec["format"], current, step, password=pwd)
                if rec.get("tar_pre"):
                    current = formats.extract_tar(current, step / "tar")
                elif len(names) == 1 and current.is_file() and formats.get(rec["format"]).kind == "raw":
                    current = current.rename(current.with_name(names[0]))
        final = out_dir / current.name
        if current.is_dir():
            shutil.copytree(current, final, dirs_exist_ok=True)
        else:
            shutil.copy2(current, final)
    return [final]
