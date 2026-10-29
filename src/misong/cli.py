"""misong — Misong command line.

Commands:
  nest     one-shot nested encrypted packaging (multi-layer, uncommon formats)
  unest    reverse a nest artifact using its .misong.json manifest
  restore  restore an artifact/folder with a .mskey portable restore key
  split    one-shot volume split (byte parts + sha256 sidecar)
  join     verify & reassemble split parts
  merge    copy /b style concat (zip offsets auto-fixed when possible)
  unwrap   recover embedded archive payload from merged/disguised files
  code     encode/decode share text: beast/mojibake/hajimi/base64/...
  relay    generate 网盘中转 packaging plan & share-copy templates
  formats  list known layer formats
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import pack

from .encoders import beast, hajimi, mojibake, plain


def _split_pswd(text: str) -> list[str | None]:
    if not text:
        return []
    return [p if p != "-" else None for p in text.split(",")]


def _parse_layers(spec: str, passwords: list[str | None],
                  header_enc: list[bool] | None) -> list[pack.LayerSpec]:
    from . import formats, pack
    if spec.lstrip().startswith("["):
        raw = json.loads(spec)
        layers = [pack.LayerSpec.from_dict(x) for x in raw]
        for i, layer in enumerate(layers):
            if i < len(passwords):
                layer.password = passwords[i]
        return layers
    keys = [k.strip() for k in spec.split(",") if k.strip()]
    layers = []
    for i, k in enumerate(keys):
        pwd = passwords[i] if i < len(passwords) else None
        f = formats.get(k)
        if pwd and not f.supports_password:
            if f.kind == "container":
                raise SystemExit(f"格式 {k} 不支持密码；把密码放到 7z/zip 层上")
            raise SystemExit(f"raw 格式 {k} 无原生密码；请在 -L 链里给它外面套一层 7z 或 zip")
        if header_enc is None:
            he = bool(pwd) and f.key == "7z"  # default: protect names on every 7z pwd layer
        else:
            he = bool(pwd) and (header_enc[i] if i < len(header_enc) else False)
        layers.append(pack.LayerSpec(fmt=k, password=pwd, header_enc=he))
    return layers


def cmd_nest(a: argparse.Namespace) -> int:
    from . import pack
    inputs = [Path(p) for p in a.inputs]
    pwds = _split_pswd(a.password)
    hens: list[bool] | None = None
    if a.header_enc:
        hens = [x.strip().lower() == "y" for x in a.header_enc.split(",")]
    layers = _parse_layers(a.layers, pwds, hens)
    from .layers import output_ext
    if a.output:
        out = Path(a.output)
        if a.disguise:
            ext = a.disguise if a.disguise.startswith(".") else "." + a.disguise
            out = out.with_suffix(ext)
    else:
        anchor = inputs[0] if len(inputs) == 1 else Path.cwd() / "multi"
        ext = "." + a.disguise.lstrip(".") if a.disguise else output_ext(layers)
        out = anchor.with_name(anchor.name + ext)
    from .preflight import require
    target = require(inputs, layers, out.parent, keep_layers=a.keep_layers)
    out = target / out.name
    manifest = pack.pack(inputs, layers, out, keep_layers=a.keep_layers, export_key=a.export_key)
    out = out.with_name(manifest["artifact"])
    print("[ok] 产物: " + ", ".join(r["name"] for r in manifest["artifacts"]))
    print(f"[ok] 清单: {out}.misong.json")
    if a.export_key:
        from .restore_key import sidecar
        print(f"[ok] 还原钥匙: {sidecar(out)}")
    for rec in manifest["layers"]:
        tag = "密码" + ("+头加密" if rec["header_enc"] else "") if rec["password"] else "无密码"
        print(f"     外层->内层: {rec.get('format', rec.get('type', 'archive')):<8} {tag:<10} {rec['size']:,}B")
    if a.disguise:
        print(f"[提示] 伪装后缀 {out.suffix}：接收方需改回真实格式或用 misong unwrap/unest")
    return 0


def cmd_unest(a: argparse.Namespace) -> int:
    from . import pack
    art = Path(a.artifact)
    mf = json.loads(Path(a.manifest).read_text(encoding="utf-8")) if a.manifest else None
    pwds = _split_pswd(a.password)
    res = pack.unest(art, Path(a.out), pwds, manifest=mf)
    for r in res:
        print(f"[ok] 解出: {r}")
    return 0


def cmd_restore(a: argparse.Namespace) -> int:
    from .restore import restore
    result = restore(Path(a.source), Path(a.out), Path(a.key_file) if a.key_file else None)
    print(f"[ok] 已校验并还原 {result['layers']} 层：{result['out']}")
    return 0


def _text_recipe_file(path):
    from .text_delivery import read_text_file, parse_recipes
    data = json.loads(read_text_file(Path(path)))
    return parse_recipes(data if isinstance(data, list) else [data])


def _text_secrets(recipes, *, video=True):
    from getpass import getpass
    from .text_contracts import RuntimeSecrets
    values = {}
    for recipe in recipes:
        for item in (*recipe.layers, recipe.carrier) if video else recipe.layers:
            if item.secret_slot:
                values[item.secret_slot] = getpass(f"密钥 [{item.secret_slot}]：")
    return RuntimeSecrets(values)


def cmd_text_deliver(a: argparse.Namespace) -> int:
    from .text_contracts import OperationContext, ErrorCode, TextOperationError
    from .text_delivery import deliver_text, read_text_file
    secrets = None
    code = None
    try:
        recipes = _text_recipe_file(a.recipes)
        secrets = _text_secrets(recipes)
        result = asyncio.run(deliver_text(
            read_text_file(Path(a.source)), recipes, Path(a.out), OperationContext(secrets),
            video_sources={r.id: a.video for r in recipes if a.video}, export_keys=a.export_key))
    except TextOperationError as error:
        code = error.code
    except Exception:
        code = ErrorCode.INVALID_RECIPE
    finally:
        if secrets is not None:
            secrets.clear()
    if code is not None:
        raise TextOperationError(code)
    print(f"[ok] 文案交付已生成并回读校验：{result['out']}")
    return 0


def cmd_text_restore(a: argparse.Namespace) -> int:
    from .text_contracts import OperationContext, RuntimeSecrets, ErrorCode, TextOperationError
    from .text_delivery import read_text_file, restore_to_file
    secrets = RuntimeSecrets()
    code = None
    try:
        recipes = _text_recipe_file(a.recipe) if a.recipe else ()
        if a.recipe and len(recipes) != 1:
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        recipe = recipes[0] if recipes else None
        if recipe is not None:
            secrets = _text_secrets((recipe,), video=a.input_kind == "video")
        result = asyncio.run(restore_to_file(
            Path(a.out), context=OperationContext(secrets),
            text=read_text_file(Path(a.source)) if a.input_kind == "text" else None,
            video=Path(a.source) if a.input_kind == "video" else None,
            key_file=Path(a.key_file) if a.key_file else None, recipe=recipe))
    except TextOperationError as error:
        code = error.code
    except Exception:
        code = ErrorCode.INVALID_RECIPE
    finally:
        secrets.clear()
    if code is not None:
        raise TextOperationError(code)
    print(f"[ok] 文案已还原（{'摘要校验通过' if result['verified'] else '手动配方，未验证原文摘要'}）：{result['out']}")
    return 0


def cmd_split(a: argparse.Namespace) -> int:
    from . import split as splitmod
    src = Path(a.file)
    size = splitmod.parse_size(a.size)
    man = splitmod.split(src, size, Path(a.out) if a.out else None, a.prefix)
    print(f"[ok] {src.name} -> {man['part_count']} 卷 (每卷<= {a.size})，清单: {a.prefix or src.name}{splitmod.SIDECAR_EXT}")
    for p in man["parts"][:6]:
        print(f"     {p['name']}  {p['size']:,}B")
    if man["part_count"] > 6:
        print(f"     ... 共 {man['part_count']} 卷")
    return 0


def cmd_join(a: argparse.Namespace) -> int:
    from . import split as splitmod
    checked = not a.no_verify and splitmod.has_verification(Path(a.part))
    out = splitmod.join(Path(a.part), Path(a.output) if a.output else None,
                        verify=not a.no_verify)
    status = "合并完成并通过校验" if checked else "合并完成（未校验：已禁用校验或未提供校验文件）"
    print(f"[ok] {status}: {out} ({out.stat().st_size:,} bytes)")
    return 0


def cmd_merge(a: argparse.Namespace) -> int:
    from . import merge
    files = [Path(f) for f in a.files]
    out = Path(a.output)
    if out.suffix == "":
        out = out.with_suffix(files[0].suffix or ".bin")
    rep = merge.concat_merge(files, out, fix_zip=not a.raw)
    print(f"[ok] 合并模式: {rep['mode']}  输出: {out} ({rep['size']:,} bytes)")
    print(f"     sha256: {rep['sha256']}")
    return 0


def cmd_unwrap(a: argparse.Namespace) -> int:
    from . import merge
    chain = _split_pswd(a.chain_pwd) if a.chain_pwd else None
    res = merge.unwrap(Path(a.file), Path(a.out), password=a.password,
                       only_format=a.format, keep_looking=a.all, chain=chain)
    for r in res:
        print(f"[ok] 提取: {r}")
    return 0


def cmd_code(a: argparse.Namespace) -> int:
    if a.file:
        text = Path(a.file).read_text(encoding="utf-8").rstrip("\n")
    elif a.text == "-":
        text = sys.stdin.read()
        if text.endswith("\n"):
            text = text[:-1]
    else:
        text = a.text
    if text is None:
        raise SystemExit("提供明文(--text '-' 读 stdin)或 --file")
    chain = [s.strip() for s in a.scheme.split(",") if s.strip()]
    out = text
    if a.op == "encode":
        for s in chain:
            out = _enc_one(s, out, a)
    else:
        for s in reversed(chain):
            out = _dec_one(s, out, a)
    if a.out:
        p = Path(a.out)
        p.write_text(out + "\n", encoding="utf-8")
        print(f"[ok] 写入 {p} ({len(out)} 字符)")
    else:
        print(out)
    return 0


def _enc_one(scheme: str, text: str, a) -> str:
    if scheme == "beast":
        return beast.encode(text, chars=a.chars or beast.DEFAULT_DICT, dialect=a.dialect)
    if scheme == "hajimi":
        return hajimi.encode(text)
    if scheme == "mojibake":
        return mojibake.encode(text, key=a.key, mode=a.mode)
    return plain.encode(scheme, text)


def _dec_one(scheme: str, cipher: str, a) -> str:
    if scheme == "beast":
        return beast.decode(cipher, chars=a.chars or beast.DEFAULT_DICT, dialect=a.dialect)
    if scheme == "hajimi":
        return hajimi.decode(cipher)
    if scheme == "mojibake":
        return mojibake.decode(cipher, key=a.key, mode=a.mode)
    return plain.decode(scheme, cipher)


def cmd_relay(a: argparse.Namespace) -> int:
    """Generate the two-stage relay packaging plan + share copy templates."""
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "version": 1,
        "form": a.form,
        "stages": [],
        "note": "上传与链接获取部分留给 RPA（rpa/ 模块）；本工具负责产物与文案",
    }
    if a.form == "simple":
        plan["stages"] = [
            {"disk": a.disk1, "payload": "guide.txt",
             "desc": "第一跳网盘只放说明txt：内含第二跳链接占位+解压密码提示位置"},
            {"disk": a.disk2, "payload": a.body or "<nest+split产物>",
             "desc": "第二跳网盘放压缩包本体（密码在视频/帖子里）"},
        ]
        guide = (
            f"【使用说明】\n"
            f"1. 本文件来自视频分享。压缩包本体在【{a.disk2}】。\n"
            f"2. 本体链接：{a.body_link or '<待RPA填入>'}\n"
            f"3. 提取码/访问码：<待RPA填入>\n"
            f"4. 解压密码看视频第 {a.pwd_hint_at or '?'} 秒 / 帖子末尾暗号。\n"
            f"5. 若提示分卷缺失，把所有分卷放同一文件夹后运行: misong join 第一卷\n"
        )
        (out_dir / "guide.txt").write_text(guide, encoding="utf-8")
        print(f"[ok] 简易版说明: {out_dir}/guide.txt")
    else:  # complex
        plan["stages"] = [
            {"disk": a.disk1, "payload": a.body or "<nest产物(带密码)套guide.txt>",
             "desc": "第一跳网盘放加密压缩包，包内是 guide.txt；包密码在视频/帖子"},
            {"disk": a.disk2, "payload": "<本体>", "desc": "guide.txt 导流到第二跳下载本体"},
        ]
        guide = (
            f"【第二跳指引】\n"
            f"本体在【{a.disk2}】: {a.body_link or '<待RPA填入>'} 提取码:<待填>\n"
            f"分卷齐后再解压；解压密码同第一层密码。\n"
        )
        (out_dir / "guide.txt").write_text(guide, encoding="utf-8")
        print(f"[ok] 复杂版说明: {out_dir}/guide.txt（记得把它塞进带密码的 nest 层再上传第一跳）")
    (out_dir / "relay-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(f"[ok] 中转计划: {out_dir}/relay-plan.json")
    return 0


def cmd_formats(_a: argparse.Namespace) -> int:
    from . import formats
    for k in formats.ORDER:
        f = formats.get(k)
        extra = []
        if f.supports_password:
            extra.append("密码")
        if f.kind == "raw":
            extra.append("单文件流")
        print(f"{k:<9} {'/'.join(f.native_exts):<28} {','.join(extra):<12} {f.note}")
    return 0


def cmd_publish(a):
    import asyncio
    from .publish import PublishOptions, prepare, publish
    from .rpa.runtime import BrowserRuntime
    from .share_options import ShareOptions
    from .text_contracts import OperationContext, RuntimeSecrets
    if a.text_recipes and a.schemes is not None:
        raise ValueError("--text-recipes 与 --schemes 不能同时指定")
    if a.plan:
        if a.text_recipes:
            raise ValueError("--plan 续跑不能覆盖文案配方")
        if a.restore_key_location != "none":
            raise ValueError("--plan 续跑沿用任务的还原钥匙，不能覆盖交付位置")
        if a.cleanup_after_upload:
            raise ValueError("--plan 续跑沿用任务保存的清理选项，不能覆盖")
        if a.task_name or a.folder_name:
            raise ValueError("--plan 续跑沿用任务名称和网盘目录名，不能覆盖")
        if a.inputs:
            raise ValueError("--plan 续跑时不能同时指定输入资源")
        if a.body_disks:
            raise ValueError("--plan 续跑沿用任务保存的网盘，不能覆盖 --body-disks")
        if a.share_expiry != "default" or a.share_access != "default":
            raise ValueError("--plan 续跑沿用任务保存的分享选项，不能在命令行覆盖")
        plan_path = Path(a.plan)
    else:
        if not a.inputs or not a.out:
            raise ValueError("新任务需要资源路径和 -o 新输出目录")
        options = PublishOptions(
            inputs=[Path(x) for x in a.inputs], out=Path(a.out),
            layers=_parse_layers(a.layers, _split_pswd(a.password), None), size=a.size,
            disguise=a.disguise, video=Path(a.video) if a.video else None, raw_merge=a.raw,
            body_disk=a.body_disk, hop_disk=a.hop_disk, form=a.form, pwd_hint=a.pwd_hint,
            schemes=() if a.text_recipes else tuple(s.strip() for s in (a.schemes if a.schemes is not None else "beast,mojibake,hajimi").split(",") if s.strip()),
            share_options=ShareOptions(a.share_expiry, a.share_access),
            body_disks=tuple(s.strip() for s in a.body_disks.split(",") if s.strip()) if a.body_disks else (),
            checksum=a.checksum, task_name=a.task_name, folder_name=a.folder_name,
            cleanup_after_upload=a.cleanup_after_upload, restore_key_location=a.restore_key_location,
            text_recipes=tuple(r.to_dict() for r in _text_recipe_file(a.text_recipes)) if a.text_recipes else None)
        plan_path = prepare(options)
    if not a.prepare:
        runtime = BrowserRuntime(headless=a.headless, timeout=a.upload_timeout, diagnostics=a.diagnostics,
                                 browser_channel=a.browser)
        secrets = RuntimeSecrets()
        try:
            saved = json.loads(plan_path.read_text(encoding="utf-8"))
            from .text_delivery import parse_recipes
            recipes = parse_recipes(saved["text_recipes"]) if "text_recipes" in saved else ()
            done = {r["recipe_id"] for r in saved.get("text_delivery", {}).get("recipes", [])
                    if r["status"] == "complete"}
            secrets = _text_secrets(tuple(r for r in recipes if r.id not in done))
            asyncio.run(publish(plan_path, runtime=runtime, key=a.key, hop_password=a.hop_password,
                                text_context=OperationContext(secrets),
                                text_video_sources={r.id: a.text_video for r in recipes if a.text_video},
                                export_text_keys=a.export_text_key))
        finally:
            secrets.clear()
    print(f"任务文件：{plan_path}")
    return 0


def cmd_account(a):
    import asyncio
    from .rpa.runtime import BrowserRuntime
    from .paths import resolve_paths
    from .rpa.drivers import PROFILES
    from .providers import PROVIDERS
    from .sharing import disk_name
    if a.op == "status":
        state_dir = resolve_paths().state
        for disk in PROVIDERS:
            if disk not in PROFILES:
                print(f"{disk}: unimplemented / 自动驱动待适配，可手动回填分享")
                continue
            state = state_dir / f"{disk}.json"
            status_path = state_dir / f"{disk}-status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))["status"] if status_path.exists() else "probe"
            print(f"{disk}: {status} / {'有本机会话（需在线确认有效）' if state.exists() else '未登录'}")
        return 0
    if not a.disk:
        raise ValueError("请指定网盘：" + ", ".join(PROFILES))
    runtime = BrowserRuntime(browser_channel=a.browser)
    asyncio.run(getattr(runtime, a.op)(disk_name(a.disk)))
    return 0


def cmd_share_import(a):
    from .publish import import_share
    text = Path(a.file).read_text(encoding="utf-8") if a.file else a.text
    import_share(Path(a.plan), a.stage, text or "")
    print("已回填；运行 misong publish --plan 任务文件 继续")
    return 0


def cmd_gui(a):
    from .desktop.main import launch
    return launch(legacy=a.legacy, debug=a.debug or None)


def cmd_doctor(a):
    from .doctor import check_environment
    from .redact import redact_data
    report = redact_data(check_environment())
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["checks"]:
            print(f"[{item['status']}] {item['message']}")
    return 0 if report["ok"] else 1


def cmd_data_migrate(a):
    from .paths import migrate_data
    migrate_data(Path(a.source), Path(a.destination))
    print("[ok] 已复制数据目录；源数据保留，已有相同内容可重复迁移")
    return 0


def build_parser() -> argparse.ArgumentParser:
    from . import __version__
    p = argparse.ArgumentParser(prog="misong", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"misong {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    doctor = sub.add_parser("doctor", help="只读检查依赖、7-Zip、Node、浏览器和桌面环境")
    doctor.add_argument("--json", action="store_true", help="输出脱敏 JSON 报告")
    doctor.set_defaults(fn=cmd_doctor)
    migration = sub.add_parser("data-migrate", help="显式复制旧数据目录到新位置，保留源数据且拒绝冲突")
    migration.add_argument("source")
    migration.add_argument("destination")
    migration.set_defaults(fn=cmd_data_migrate)

    n = sub.add_parser("nest", help="一键多层嵌套加密打包")
    n.add_argument("inputs", nargs="+", help="要加密的文件/目录（多个则先归拢）")
    n.add_argument("-L", "--layers", required=True,
                   help="内到外格式链如 lz4,zip,7z；或 JSON 层数组（type=archive/cover/split/rename）")
    n.add_argument("-P", "--password", default="",
                   help="按层对齐的密码，逗号分隔，'-' 表示该层无密码")
    n.add_argument("-H", "--header-enc", default="",
                   help="按层对齐的 7z 头加密开关 y/-，默认所有有密码的7z层都开")
    n.add_argument("-o", "--output", help="产物路径（默认 输入名+外层扩展名）")
    n.add_argument("--disguise", help="最外层伪装扩展名，如 .mp4/.lz4/.png")
    n.add_argument("--keep-layers", action="store_true", help="保留每层中间产物")
    n.add_argument("--export-key", action="store_true", help="明确导出可直接还原的 .mskey 钥匙（包含层密码，默认不导出）")
    n.set_defaults(fn=cmd_nest)

    u = sub.add_parser("unest", help="按清单逆向解开 nest 产物")
    u.add_argument("artifact")
    u.add_argument("-P", "--password", default="", help="外层->内层顺序的密码链")
    u.add_argument("-o", "--out", required=True)
    u.add_argument("--manifest", help="手动指定 .misong.json（默认找同名 sidecar）")
    u.set_defaults(fn=cmd_unest)

    restore = sub.add_parser("restore", help="用 .mskey 钥匙一键校验、合卷和逐层还原")
    restore.add_argument("source", help="最终产物、任意分卷或下载文件夹")
    restore.add_argument("--key-file", help="还原钥匙；省略时自动寻找同目录唯一的 .mskey")
    restore.add_argument("-o", "--out", required=True, help="空的还原目录")
    restore.set_defaults(fn=cmd_restore)

    delivery = sub.add_parser("text-deliver", help="按有序方案生成文字/帧语视频，可显式导出 .tkey")
    delivery.add_argument("source", help="UTF-8 原文文件，保留换行")
    delivery.add_argument("--recipes", required=True, help="公开配方 JSON 文件（不含密码）")
    delivery.add_argument("--video", help="视频方案使用的本地源视频；运行时联网操作官网")
    delivery.add_argument("--export-key", action="append", default=[], metavar="RECIPE_ID",
                          help="明确为此方案导出 .tkey，可重复；默认不导出")
    delivery.add_argument("-o", "--out", required=True, help="尚不存在的输出目录")
    delivery.set_defaults(fn=cmd_text_deliver)

    tr = sub.add_parser("text-restore", help="按 .tkey 或手动配方还原文字/本地视频")
    tr.add_argument("source", help="UTF-8 文字文件或本地视频")
    tr.add_argument("--input-kind", choices=["text", "video"], required=True)
    tr_source = tr.add_mutually_exclusive_group(required=True)
    tr_source.add_argument("--key-file", help="敏感文案还原钥匙 .tkey")
    tr_source.add_argument("--recipe", help="单个手动公开配方 JSON，密码交互输入")
    tr.add_argument("-o", "--out", required=True, help="尚不存在的 UTF-8 输出文件")
    tr.set_defaults(fn=cmd_text_restore)

    s = sub.add_parser("split", help="一键分卷")
    s.add_argument("file")
    s.add_argument("-s", "--size", default="4000M", help="每卷大小如 4000MB/1GB；只填数字默认 MB，未超过则不分卷")
    s.add_argument("-o", "--out", help="输出目录（默认源文件旁）")
    s.add_argument("--prefix", help="分卷命名前缀（默认源文件名）")
    s.set_defaults(fn=cmd_split)

    j = sub.add_parser("join", help="分卷合并+校验")
    j.add_argument("part", help="任意一个 .001 分卷（兼容旧 .partNNN）")
    j.add_argument("-o", "--output")
    j.add_argument("--no-verify", action="store_true")
    j.set_defaults(fn=cmd_join)

    m = sub.add_parser("merge", help="copy /b 式合并(视频+压缩包等)")
    m.add_argument("files", nargs="+", help="按顺序合并的文件，视频在前放第一个")
    m.add_argument("-o", "--output", required=True)
    m.add_argument("--raw", action="store_true", help="纯拼接，不做 zip 偏移修正")
    m.set_defaults(fn=cmd_merge)

    w = sub.add_parser("unwrap", help="从合并/伪装文件中提取归档载荷")
    w.add_argument("file")
    w.add_argument("-o", "--out", required=True)
    w.add_argument("-P", "--password", default=None)
    w.add_argument("--chain-pwd", help="逐层密码(外->内)逗号分隔，'-' 无密码；自动嗅探连剥")
    w.add_argument("--format", help="限定载荷格式 zip/7z/gz/xz/bz2/zst/lz4")
    w.add_argument("--all", action="store_true", help="继续找后续嵌套载荷")
    w.set_defaults(fn=cmd_unwrap)

    c = sub.add_parser("code", help="分享文本编解码: beast/mojibake/hajimi/base64/...")
    c.add_argument("op", choices=["encode", "decode"])
    c.add_argument("--scheme", "-S", required=True,
                   help="方案(可逗号串联如 beast,base64)：beast|mojibake|hajimi|"
                        "base64|base64url|base32|base85|hex|url|reverse|rot13|trunc")
    c.add_argument("--text", "-T", help="文本；decode 时也可用 --file；'-' 读 stdin")
    c.add_argument("--file", "-F", help="从文件读")
    c.add_argument("-o", "--out", help="结果写入文件")
    c.add_argument("--chars", help="兽音4字符集(如 点赞投币)")
    c.add_argument("--dialect", default="auto", help="兽音方言: web|sdk|pojie|auto")
    c.add_argument("--key", default="ABRACADABRA", help="魔曰密钥(魔咒)")
    c.add_argument("--mode", default="wenyan", help="魔曰模式: wenyan|old")
    c.set_defaults(fn=cmd_code)

    r = sub.add_parser("relay", help="生成网盘中转计划与文案(上传部分留给RPA)")
    r.add_argument("--form", choices=["simple", "complex"], required=True)
    r.add_argument("--disk1", default="飞猫盘")
    r.add_argument("--disk2", default="夸克")
    r.add_argument("--body", help="本体产物路径(nest/split后的)")
    r.add_argument("--body-link", help="第二跳链接(RPA回填)")
    r.add_argument("--pwd-hint-at", help="密码在视频中的位置提示")
    r.add_argument("-o", "--out", default="relay-out")
    r.set_defaults(fn=cmd_relay)

    f = sub.add_parser("formats", help="列出支持的层格式")
    f.set_defaults(fn=cmd_formats)
    pub = sub.add_parser("publish", help="打包、上传、中转、生成加密分享文案；支持断点续跑")
    pub.add_argument("inputs", nargs="*")
    pub.add_argument("--plan", help="继续已有 relay-plan.json")
    pub.add_argument("--task-name", default="", help="任务名称；留空取第一个资源名")
    pub.add_argument("--folder-name", default="", help="新建网盘目录名；多盘同名，中转第一跳加 -hop；已存在则拒绝")
    pub.add_argument("-o", "--out", help="新任务输出目录（必须不存在）")
    pub.add_argument("-L", "--layers", default="lz4,7z")
    pub.add_argument("-P", "--password", default="", help="按层对应的密码链，建议 GUI 输入以免进入命令历史")
    pub.add_argument("-s", "--size", default="1900M", help="默认 1900MB；只填数字按 MB；空字符串禁用分卷")
    pub.add_argument("--disguise", default="")
    pub.add_argument("--checksum", action="store_true", help="额外上传标准 SHA-256 校验文件（默认关）")
    pub.add_argument("--restore-key-location", choices=["none", "local", "body", "hop"], default="none",
                     help="还原钥匙：不导出/仅本地/随本体/随第一跳；明确选择后才导出")
    pub.add_argument("--cleanup-after-upload", action="store_true",
                     help="所有网盘上传并分享完成后，删除本任务加工产物；保留源文件及任务记录（默认关）")
    pub.add_argument("--video", help="可选门面视频")
    pub.add_argument("--raw", action="store_true", help="兼容旧参数；publish 的门面视频现自动嵌入开头")
    pub.add_argument("--form", choices=["direct", "simple", "complex"], default="direct")
    pub.add_argument("--body-disk", default="quark")
    pub.add_argument("--body-disks", help="多个本体网盘，用逗号分隔；同一份产物逐盘上传")
    pub.add_argument("--hop-disk", default="feimao")
    pub.add_argument("--hop-password", help="复杂中转第一跳归档密码（不写入计划）")
    pub.add_argument("--share-expiry", choices=["default", "1", "2", "3", "4", "5", "6", "7", "30", "60", "180", "365", "forever"], default="default",
                     help="所有阶段统一分享有效期；数字为天数，不支持的组合在上传前拒绝")
    pub.add_argument("--share-access", choices=["default", "none", "code"], default="default",
                     help="所有阶段统一提取码：平台默认/无/自动生成")
    pub.add_argument("--pwd-hint", default="请向分享者获取解压密码。")
    pub.add_argument("--schemes", default=None)
    pub.add_argument("--text-recipes", help="有序文案方案 JSON；与旧 --schemes 互斥")
    pub.add_argument("--text-video", help="本次文案视频载体的源视频，续跑时重新指定")
    pub.add_argument("--export-text-key", action="append", default=[], metavar="RECIPE_ID",
                     help="本次明确为指定方案导出 .tkey；不保存为任务偏好")
    pub.add_argument("--key", default="ABRACADABRA")
    pub.add_argument("--prepare", action="store_true", help="仅生成产物与任务，不联网")
    pub.add_argument("--headless", action="store_true", help="已有登录态后无头执行")
    pub.add_argument("--upload-timeout", type=int, default=1800, help="单文件确认超时秒数")
    pub.add_argument("--diagnostics", action="store_true", help="失败时保存私密诊断快照到 rpa/state，不入库")
    pub.add_argument("--browser", choices=["chromium", "chrome", "msedge"], help="使用自带 Chromium 或已安装的正式版 Chrome/Edge；默认复用账号选择")
    pub.set_defaults(fn=cmd_publish)
    ac = sub.add_parser("account", help="网盘登录、探测与驱动状态")
    ac.add_argument("op", choices=["login", "probe", "status"])
    ac.add_argument("disk", nargs="?")
    ac.add_argument("--browser", choices=["chromium", "chrome", "msedge"], help="登录/探测浏览器；启动成功后记住选择供后续发布使用")
    ac.set_defaults(fn=cmd_account)
    imp = sub.add_parser("share-import", help="手动上传后回填分享文本")
    imp.add_argument("--plan", required=True)
    imp.add_argument("--stage", choices=["body", "hop"], required=True)
    source = imp.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--file")
    imp.set_defaults(fn=cmd_share_import)
    gui = sub.add_parser("gui", help="打开中文桌面界面（Edge WebView2）")
    gui.add_argument("--legacy", action="store_true", help="使用旧版 Tk 界面")
    gui.add_argument("--debug", action="store_true", help="打开 WebView 开发者工具")
    gui.set_defaults(fn=cmd_gui)
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8")
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except FileNotFoundError as e:
        print(f"[err] 文件不存在: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[err] {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
