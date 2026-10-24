"""Stand-alone module workflows used by the desktop UI.

The full pipeline stays in publish.prepare/publish. These helpers let each block
(encrypt-pack, upload-share) run on its own while reusing pack/merge/split and the
same v2 relay-plan checkpoints, so standalone uploads resume exactly like pipeline jobs.
Passwords are never written to disk here.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from . import formats, merge, pack, split, preflight
from .layers import migrate, output_ext, validate
from .jobs import fingerprint, save_json
from .providers import PROVIDERS
from .share_options import ShareOptions
from .sharing import COPY_SCHEMES, disk_name
from .metadata import MANIFEST_EXTS, SPLIT_EXTS, TASK_NAMES

META_NAMES = TASK_NAMES
META_NAME = META_NAMES[0]
# Fixed list offered by the UI: common media suffixes that netdisks accept without re-encoding.
DISGUISE_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".png", ".jpg")


def write_meta(folder: Path, kind: str, title: str, **extra) -> None:
    data = {"kind": kind, "title": title, "created": datetime.now().isoformat(timespec="seconds"), **extra}
    save_json(Path(folder) / META_NAME, data)


def read_meta(folder: Path) -> dict:
    path = next((Path(folder) / name for name in META_NAMES if (Path(folder) / name).is_file()), None)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path is not None else {}
    except ValueError:
        return {}


def update_meta(folder: Path, **changes) -> dict:
    """Merge fields into misong-task.json, keeping kind/created of an existing task."""
    data = read_meta(folder)
    data.update(changes)
    save_json(Path(folder) / META_NAME, data)
    return data


def title_for(inputs) -> str:
    names = [Path(p).name for p in inputs]
    if not names:
        return "未命名任务"
    return names[0] if len(names) == 1 else f"{names[0]} 等 {len(names)} 项"


def publication_names(task_name="", folder_name="") -> tuple[str, str]:
    """Validate optional display title and a single portable remote directory name."""
    title, folder = str(task_name or "").strip(), str(folder_name or "").strip()
    if len(title) > 120 or any(ord(c) < 32 for c in title):
        raise ValueError("任务名称最多 120 个字符，不能含控制字符")
    if folder and (len(folder) > 100 or folder in (".", "..") or folder.endswith(".") or
                   re.search(r'[<>:"/\\|?*\x00-\x1f]', folder) or
                   re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", folder)):
        raise ValueError("网盘目录名最多 100 个字符，不能是路径或含特殊字符、保留名称")
    return title, folder


def upload_stage(job_id, disk, records, index=0, folder_name=""):
    return {"id": "body" if index == 0 else "body-" + disk, "role": "body", "disk": disk,
            "folder": folder_name or f"misong-{job_id}-body-{disk}", "files": records,
            "state": "pending", "uploaded": {}, **({"custom_folder": True} if folder_name else {})}


def _fresh_dir(out_dir: Path, inputs: list[Path]) -> Path:
    target = Path(out_dir).resolve()
    if any(p == target or (p.is_dir() and p in target.parents) for p in inputs):
        raise ValueError("输出目录不能位于输入资源内部")
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"输出目录必须为空：{target}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def pack_only(inputs, layers: list[pack.LayerSpec], out_dir: Path, *, size: str = "", disguise: str = "",
              video: Path | None = None, raw_merge: bool = False, checksum: bool = False, notify=print) -> dict:
    """Encrypt-pack (optionally merge into a cover video and split) without any upload plan."""
    inputs = [Path(p).resolve(strict=True) for p in inputs]
    if not inputs:
        raise ValueError("请先选择要打包的资源")
    if not layers:
        raise ValueError("请至少设置一层格式")
    if len({p.name.casefold() for p in inputs}) != len(inputs):
        raise ValueError("多个输入的文件名不能相同")
    if disguise and ("." + disguise.strip().lstrip(".")).lower() not in DISGUISE_EXTS:
        raise ValueError("伪装后缀仅支持：" + " ".join(DISGUISE_EXTS))
    layers = migrate(layers, disguise=disguise, video=video, size=size)
    validate(layers, inputs)
    target = preflight.require(inputs, layers, out_dir, notify)
    target = _fresh_dir(target, inputs)
    base = inputs[0].stem if len(inputs) == 1 and inputs[0].is_file() else (inputs[0].name if len(inputs) == 1 else "bundle")
    artifact = target / (base + output_ext(layers))
    notify("打包：正在按层生成最终产物")
    manifest = pack.pack(inputs, layers, artifact)
    for record in reversed(manifest["layers"]):
        if record["type"] != "split":
            continue
        sm = record["split_manifest"]
        outcome = f"生成 {sm['part_count']} 卷" if sm["part_count"] > 1 else "未超过阈值，保留单文件"
        if record["index"] < len(layers) - 1:
            outcome += "；后续层已继续处理分卷层产物"
        notify(f"第 {record['index'] + 1} 层分卷结果：输入 {sm['source_size'] / 1024**2:.3f} MB，"
               f"每卷 {sm['part_size'] / 1024**2:.3f} MB，{outcome}")
    outputs = [target / rec["name"] for rec in manifest["artifacts"]]
    if checksum:
        outputs.append(write_checksums(outputs, target / (base + ".sha256")))
    chain = ",".join(x.fmt if x.type == "archive" else x.type for x in reversed(layers))
    first = outputs[0]
    write_restore(target, first, manifest)
    write_meta(target, "pack", title_for(inputs), chain=chain, artifact=str(first),
               artifacts=[str(p) for p in outputs])
    notify(f"完成：{target}")
    return {"out": str(target), "artifact": str(first), "chain": chain,
            "files": [_file_info(p) for p in outputs], "parts": []}


def write_checksums(files, path):
    path = Path(path)
    path.write_text("".join(f"{pack._sha256(p)}  {p.name}\n" for p in files), encoding="utf-8")
    return path


def is_local_metadata(path):
    name = Path(path).name.lower()
    return (name.endswith((*MANIFEST_EXTS, *SPLIT_EXTS)) or
            name in ("restore.txt", *META_NAMES, "relay-plan.json"))


def write_restore(target, first, manifest):
    chain = ",".join(r.get("format", r["type"]) for r in manifest["layers"])
    Path(target, "RESTORE.txt").write_text(
        "【还原说明 · 本地保留】\n下载全部最终产物/分卷到同一目录。\n"
        f'有清单：misong unest "{first.name}" -o restored -P="外层到内层密码链"\n'
        f'无清单：misong unwrap "{first.name}" -o restored --chain-pwd="归档层外到内密码链"\n'
        "unest 每层对齐，cover/split/rename 用 - 占位；unwrap 只对齐归档层。\n"
        "分卷也可先 misong join 第一卷.001，再解包；7-Zip / WinRAR 从 .001 打开。\n"
        f"完整层序（外到内）：{chain}\n清单、RESTORE.txt 只留本地；密码请单独告知接收方。\n",
        encoding="utf-8")


def _file_info(path: Path) -> dict:
    return {"path": str(path), "name": path.name, "size": path.stat().st_size}


def prepare_upload(files, out_dir: Path, body_disks, share_options: ShareOptions | None = None,
                   schemes=(), notify=print, *, checksum=False, task_name="", folder_name="") -> Path:
    """Create a direct-share v2 plan for existing local files; publish() then uploads and shares."""
    from .rpa.drivers import PROFILES
    title, folder_name = publication_names(task_name, folder_name)
    share_options = share_options or ShareOptions()
    files = [Path(p).resolve(strict=True) for p in files if not is_local_metadata(p) and
             (checksum or Path(p).suffix.lower() != ".sha256")]
    if not files:
        raise ValueError("请先选择要上传的文件")
    if any(not p.is_file() for p in files):
        raise ValueError("上传模块只接受文件；文件夹请先用加密打包生成归档")
    if len({p.name.casefold() for p in files}) != len(files):
        raise ValueError("同一批上传的文件名不能重复")
    disks = list(dict.fromkeys(map(disk_name, body_disks)))
    if not disks:
        raise ValueError("请至少选择一个网盘")
    for disk in disks:
        if disk not in PROFILES:
            raise ValueError(f"{PROVIDERS.get(disk, {}).get('label', disk)} 暂无自动上传驱动，可在任务中心手动回填分享")
        share_options.validate_disk(disk)
    if any(s not in COPY_SCHEMES for s in schemes):
        raise ValueError("文案方案无效：" + ",".join(schemes))
    target = _fresh_dir(out_dir, files)
    job_id = uuid.uuid4().hex[:12]
    notify(f"校验：正在计算 {len(files)} 个文件的 SHA-256")
    if checksum:
        files = [p for p in files if p.suffix.lower() != ".sha256"]
        files.append(write_checksums(files, target / "checksums.sha256"))
    records = [fingerprint(p) for p in files]
    stages = [upload_stage(job_id, disk, records, i, folder_name)
              for i, disk in enumerate(disks)]
    plan = {"version": 2, "id": job_id, "form": "direct", "stages": stages, "schemes": list(schemes),
            "pwd_hint": "", "state": "prepared", "share_options": share_options.to_dict()}
    path = target / "relay-plan.json"
    save_json(path, plan)
    write_meta(target, "upload", title or title_for(files), folder_name=folder_name)
    notify(f"已准备：{len(files)} 个文件 → {len(disks)} 个网盘")
    return path
