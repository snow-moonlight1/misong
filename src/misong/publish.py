"""Package -> upload body -> fill guide -> upload hop -> encrypted share copy."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from . import cleanup, formats, merge, pack, split, workflows, preflight
from .layers import migrate, validate
from .jobs import exclusive, fingerprint, save_json, verify_files
from .sharing import COPY_SCHEMES, ShareInfo, disk_name, parse_share, write_copy
from .share_options import ShareOptions
from .providers import PROVIDERS


class Paused(RuntimeError):
    pass


@dataclass
class PublishOptions:
    inputs: list[Path]
    out: Path
    layers: list[pack.LayerSpec] = field(default_factory=lambda: [pack.LayerSpec("7z")])
    size: str = "1900M"
    disguise: str = ""
    video: Path | None = None
    raw_merge: bool = False
    body_disk: str = "quark"
    hop_disk: str = "feimao"
    form: str = "direct"
    pwd_hint: str = "请向分享者获取解压密码。"
    schemes: tuple[str, ...] = ("beast", "mojibake", "hajimi")
    share_options: ShareOptions = field(default_factory=ShareOptions)
    body_disks: tuple[str, ...] = ()
    checksum: bool = False
    task_name: str = ""
    folder_name: str = ""
    cleanup_after_upload: bool = False
    restore_key_location: str = "none"
    text_recipes: tuple[dict, ...] | None = None


def prepare(options: PublishOptions, notify=print) -> Path:
    o = options
    title, folder_name = workflows.publication_names(o.task_name, o.folder_name)
    if o.form not in ("direct", "simple", "complex"):
        raise ValueError("中转模式必须为 direct/simple/complex")
    if o.restore_key_location not in ("none", "local", "body", "hop"):
        raise ValueError("还原钥匙位置必须是 none/local/body/hop")
    if o.restore_key_location == "hop" and o.form == "direct":
        raise ValueError("随第一跳交付钥匙需要选择中转分享")
    body_disks = list(dict.fromkeys(map(disk_name, o.body_disks or (o.body_disk,))))
    for disk in body_disks + ([o.hop_disk] if o.form != "direct" else []):
        o.share_options.validate_disk(disk)
    if not o.inputs or not o.layers:
        raise ValueError("请选择资源和至少一层格式")
    text_recipes = None
    if o.text_recipes is not None:
        from .text_delivery import parse_recipes
        text_recipes = parse_recipes(list(o.text_recipes))
        if o.schemes:
            raise ValueError("新文案配方与旧 schemes 不能同时指定")
    elif not o.schemes or any(s not in COPY_SCHEMES for s in o.schemes):
        raise ValueError("请选择有效文案方案：" + ",".join(COPY_SCHEMES))
    inputs = [p.resolve(strict=True) for p in o.inputs]
    if len({p.name.casefold() for p in inputs}) != len(inputs):
        raise ValueError("多个输入的文件名不能相同")
    target = o.out.resolve()
    if any(p == target or p.is_dir() and p in target.parents for p in inputs):
        raise ValueError("输出目录不能位于输入资源内部")
    layers = migrate(o.layers, disguise=o.disguise, video=o.video, size=o.size)
    validate(layers, inputs)
    target = preflight.require(inputs, layers, target, notify)
    # Never overwrite an existing task or its upload checkpoints.
    target.mkdir(parents=True, exist_ok=False)
    job_id = uuid.uuid4().hex[:12]
    result = workflows.pack_only(inputs, layers, target / "body", checksum=o.checksum,
                                 export_key=o.restore_key_location != "none", notify=notify)
    files = [Path(rec["path"]) for rec in result["files"]]
    records = [fingerprint(p) for p in files]
    generated_records = list(records)
    key_record = fingerprint(Path(result["restore_key"])) if result.get("restore_key") else None
    if key_record and o.restore_key_location == "body":
        records.append(key_record)
    stages = [workflows.upload_stage(job_id, disk, records, i, folder_name)
              for i, disk in enumerate(body_disks)]
    if o.form != "direct":
        # Stored first for compatibility with the original relay-plan stage ordering.
        stages.insert(0, {"id": "hop", "disk": disk_name(o.hop_disk),
                          "folder": folder_name + "-hop" if folder_name else f"misong-{job_id}-hop",
                          **({"custom_folder": True} if folder_name else {}),
                          "depends_on": "body", "depends_on_all": [s["id"] for s in stages],
                          "files": [], "state": "pending", "uploaded": {}})
    plan = {"version": 2, "id": job_id, "form": o.form, "stages": stages,
            "schemes": list(o.schemes), "pwd_hint": o.pwd_hint, "state": "prepared",
            "share_options": o.share_options.to_dict()}
    if text_recipes is not None:
        plan["text_recipes"] = [r.to_dict() for r in text_recipes]
    sources = inputs + [Path(layer.video) for layer in layers if layer.type == "cover" and layer.video]
    if key_record:
        plan["restore_key"] = {"location": o.restore_key_location, "file": key_record}
    # Retain the exported key even if uploaded artifacts are explicitly cleaned.
    plan["local_cleanup"] = cleanup.inventory(target, sources, generated_records, o.cleanup_after_upload)
    path = target / "relay-plan.json"
    save_json(path, plan)
    workflows.write_meta(target, "pipeline", title or workflows.title_for(inputs), folder_name=folder_name)
    notify(f"已准备：{len(files)} 个待上传文件；任务 {path}")
    return path


def _guide(plan: dict, body_shares: list[ShareInfo]) -> str:
    if plan.get("restore_key", {}).get("location") in ("body", "hop"):
        return ("【第二跳资源下载指引】\n" + _share_text(body_shares) + "\n"
                "任选一个本体网盘，下载全部最终产物/分卷；同时下载 .mskey 还原钥匙。\n"
                "在密送的「一键还原」页拖入下载目录和钥匙，即可校验并逐层还原。\n")
    return ("【第二跳资源下载指引】\n" + _share_text(body_shares) + "\n"
            + ("任选一个网盘，下载该网盘目录内的全部最终文件/分卷。\n" if len(body_shares) > 1 else "")
            + plan.get("pwd_hint", "请向分享者获取解压密码。")
            + "\n下载所有分卷至同一目录，从 .001 打开或用 misong unwrap --chain-pwd 还原；密码由分享者单独告知。\n")


def _share_text(shares):
    if len(shares) == 1:
        return shares[0].text()
    return "\n\n".join(f"【{PROVIDERS.get(share.disk, {}).get('label', share.disk)}】\n{share.text()}" for share in shares)


def import_share(plan_path: Path, stage_id: str, text: str):
    """Manual fallback and link replacement invalidate downstream, stale guide uploads."""
    path = Path(plan_path).resolve()
    with exclusive(path.with_suffix(".lock")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("version") != 2:
            raise ValueError("只支持新版 publish 任务")
        stage = next((s for s in plan["stages"] if s["id"] == stage_id), None)
        if stage is None or not stage["files"]:
            raise ValueError("该阶段文件尚未生成或不存在，请先继续发布")
        info = parse_share(text, stage["disk"]).to_dict()
        changed = stage.get("share") != info
        stage["share"] = info
        stage["state"] = "shared"
        stage["manual"] = True  # a hand-filled link proves nothing about the automatic driver
        if changed:
            for child in plan["stages"]:
                if child.get("depends_on") == stage_id or stage_id in child.get("depends_on_all", []):
                    child.pop("share", None)
                    child["files"] = []
                    child["uploaded"] = {}
                    child["state"] = "pending"
                    child["folder"] = f"misong-{plan['id']}-{child['id']}-{uuid.uuid4().hex[:6]}"
                    child.pop("custom_folder", None)
                    child.pop("folder_created", None)
            plan.pop("final_share", None)
            plan.pop("final_shares", None)
            plan["state"] = "prepared"
        save_json(path, plan)


async def publish(plan_path: Path, *, runtime=None, notify=print, cancel: Event | None = None,
                  key="ABRACADABRA", hop_password: str | None = None,
                  text_context=None, text_video_sources=None, export_text_keys=(), text_carrier=None) -> dict:
    """Runtime injection lets tests exercise the full orchestration without network."""
    from .rpa.runtime import BrowserRuntime
    plan_path = Path(plan_path).resolve()
    with exclusive(plan_path.with_suffix(".lock")):
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("version") != 2:
            raise ValueError("旧版中转模板请先用 misong publish --prepare 新建任务，避免上传占位内容")
        runtime = runtime or BrowserRuntime(notify=notify, cancel=cancel)
        stages = {s["id"]: s for s in plan["stages"]}
        bodies = [s for s in plan["stages"] if s["id"] != "hop"]
        if not bodies or not any(s["id"] == "body" for s in bodies):
            raise ValueError("任务缺少本体阶段")
        order = bodies + ([stages["hop"]] if "hop" in stages else [])
        share_options = ShareOptions(**plan.get("share_options", {}))
        for stage in order:
            if not stage.get("share"):
                share_options.validate_disk(stage["disk"])
        def checkpoint():
            save_json(plan_path, plan)
        def check_cancel():
            if cancel and cancel.is_set():
                raise Paused("已暂停；可以从任务文件继续")
        try:
            plan["state"] = "running"
            checkpoint()
            for stage in order:
                check_cancel()
                if stage["id"] == "hop" and not stage["files"]:
                    body = [ShareInfo(**s["share"]) for s in bodies]
                    guide = plan_path.parent / "guide.txt"
                    guide.write_text(_guide(plan, body), encoding="utf-8")
                    payload = guide
                    if plan["form"] == "complex":
                        if not hop_password:
                            raise Paused("复杂中转需要第一跳压缩包密码；继续时提供 --hop-password")
                        payload = plan_path.parent / "guide.7z"
                        pack.pack([guide], [pack.LayerSpec("7z", hop_password, True)], payload)
                    cleanup.register(plan, fingerprint(guide))
                    if payload != guide:
                        cleanup.register(plan, fingerprint(payload))
                    stage["files"] = [fingerprint(payload)]
                    restore_info = plan.get("restore_key", {})
                    if restore_info.get("location") == "hop":
                        stage["files"].append(restore_info["file"])
                    checkpoint()
                verify_files([rec for rec in stage["files"]
                              if not (stage.get("share") and cleanup.owns(plan, rec))])
                if stage.get("share"):
                    notify(f"复用分享：{stage['id']} / {stage['disk']}")
                    continue
                notify(f"上传：{stage['id']} / {stage['disk']}")
                async with runtime.open(stage["disk"]) as (driver, page):
                    if stage.get("custom_folder") and not stage.get("folder_created"):
                        def folder_created():
                            stage["folder_created"] = True
                            checkpoint()
                        driver.require_new_folder(stage["folder"], folder_created)
                    if not share_options.is_default:
                        driver.configure_share(share_options)
                    for rec in stage["files"]:
                        check_cancel()
                        if rec["path"] in stage["uploaded"]:
                            continue
                        targets = await driver.upload(page, [Path(rec["path"])], stage["folder"])
                        if not targets:
                            raise RuntimeError("网盘未返回上传目标，任务已保留")
                        stage["uploaded"][rec["path"]] = targets
                        stage["state"] = "uploading"
                        checkpoint()
                        notify(f"已上传 {len(stage['uploaded'])}/{len(stage['files'])}：{Path(rec['path']).name}")
                    stage["state"] = "uploaded"
                    checkpoint()
                    targets = list(dict.fromkeys(t for value in stage["uploaded"].values() for t in value))
                    share = await driver.share(page, targets)
                    if not share.url:
                        raise RuntimeError("分享链接为空，已保留上传检查点")
                    stage["share"] = share.to_dict()
                    stage["state"] = "shared"
                    stage.pop("manual", None)
                    checkpoint()
                check_cancel()
            final_shares = [ShareInfo(**s["share"]) for s in ([stages["hop"]] if "hop" in stages else bodies)]
            final = final_shares[0]
            if "text_recipes" in plan:
                notify("文案：网盘已分享，按交付方案逐个生成（已完成方案不重复生成）")
                from .text_delivery import deliver_shared
                from .text_contracts import OperationContext
                plan["final_share"] = final.to_dict()
                plan["final_shares"] = [s.to_dict() for s in final_shares]
                plan.setdefault("text_delivery", {"version": 1, "share_complete": True, "recipes": []})
                checkpoint()
                await deliver_shared(plan, _share_text(final_shares), plan_path.parent / "copy",
                                     text_context or OperationContext(cancel=cancel), checkpoint,
                                     video_sources=text_video_sources, export_keys=export_text_keys,
                                     carrier=text_carrier)
                copies = {}  # new results are artifact metadata, not plaintext in job JSON
            else:
                notify("文案：生成兽曰 / 魔曰 / 哈基米等选定版本")
                copies = write_copy(plan_path.parent / "copy", final, plan["schemes"], key=key,
                                    text=_share_text(final_shares))
            plan["state"] = "complete"
            plan.pop("error", None)
            plan["final_share"] = final.to_dict()
            plan["final_shares"] = [s.to_dict() for s in final_shares]
            checkpoint()
            notify(f"完成：{plan_path.parent / 'copy'}")
        except BaseException as e:
            plan["state"] = "paused" if (isinstance(e, (Paused, KeyboardInterrupt, asyncio.CancelledError))
                                         or getattr(e, "code", None) == "cancelled") else "blocked"
            # Do not persist arbitrary exception strings, which may contain authentication URLs.
            plan["error"] = {"type": type(e).__name__, "stage": "text_delivery" if plan.get("text_delivery", {}).get("share_complete")
                             else stage.get("id", "copy") if 'stage' in locals() else "start"}
            checkpoint()
            if plan["error"]["stage"] == "text_delivery":
                notify("分享完成、文案未完成：继续任务只重试未完成的文案方案，不会重新上传或分享")
            raise
        # Publication is durable before cleanup. Failures here never relabel the share as blocked.
        cleanup.remove_generated(plan_path, plan, checkpoint, notify)
        return {"plan": plan, "copies": copies}
