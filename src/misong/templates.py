"""Public template JSON import/export (roadmap v0.2 item 7).

A template file only carries public packing options and public text recipes:

    {"schema_version": 1, "kind": "misong-templates", "exported_at": "...",
     "templates": [{"name": ..., "layers": [...], "disguise": "", "size": "",
                    "options": {"raw_merge": false, "checksum": false},
                    "text_recipes": [<DeliveryRecipe.to_dict()>]}]}

Passwords, accounts, resource / cover-video paths, sessions, key content, copy
text and the "export key" selection are not part of the format; unknown fields,
unknown versions, broken structures and oversize input are rejected. Importing
only validates data and returns template dicts for the caller to store; it
never runs commands, opens URLs, reads other files or starts a task.
Layer semantics reuse ``desktop.api.Api`` cleaning plus ``layers.validate``;
recipes reuse ``text_layers.DeliveryRecipe`` strict whitelists.
"""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
KIND = "misong-templates"
MAX_FILE_BYTES = 256 * 1024
MAX_TEMPLATES = 30          # same limit as desktop.api.MAX_TEMPLATES
MAX_NAME = 24               # same limit as Api.save_template
MAX_LAYERS = 32
TOP_FIELDS = {"schema_version", "kind", "templates"}
TOP_OPTIONAL = {"exported_at"}
TEMPLATE_FIELDS = {"name", "layers"}
TEMPLATE_OPTIONAL = {"disguise", "size", "options", "text_recipes"}
OPTION_FIELDS = ("raw_merge", "checksum")
LAYER_FIELDS = {
    "archive": ({"fmt", "locked", "header_enc"}, {"type", "level"}),
    "cover": ({"type", "video"}, set()),
    "split": ({"type", "size"}, set()),
    "rename": ({"type", "ext"}, set()),
}


class TemplateError(ValueError):
    """Template file rejected; message is safe to show (no file content echoed)."""


def _fail(message: str):
    raise TemplateError(message)


def _fields(data, required: set, optional: set, where: str) -> None:
    if not isinstance(data, dict):
        _fail(f"{where}结构错误")
    keys = set(data)
    if not all(isinstance(k, str) for k in keys):
        _fail(f"{where}结构错误")
    if required - keys:
        _fail(f"{where}缺少字段：" + "、".join(sorted(required - keys)))
    unknown = keys - required - optional
    if unknown:
        _fail(f"{where}含未知字段：" + "、".join(sorted(unknown))[:200])


def _name(value) -> str:
    if not isinstance(value, str):
        _fail("模板名称必须是文本")
    name = value.strip()
    if not name or len(name) > MAX_NAME or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in name):
        _fail(f"模板名称必须为 1–{MAX_NAME} 个字符且不含控制字符")
    return name


def _layer(raw, index: int) -> dict:
    where = f"第 {index + 1} 层"
    if not isinstance(raw, dict):
        _fail(where + "结构错误")
    kind = raw.get("type", "archive")
    if kind not in LAYER_FIELDS:
        _fail(where + "层类型未知")
    required, optional = LAYER_FIELDS[kind]
    _fields(raw, required, optional, where)
    if kind == "archive":
        if not isinstance(raw["fmt"], str) or not isinstance(raw["locked"], bool) \
                or not isinstance(raw["header_enc"], bool):
            _fail(where + "字段类型错误")
        if "level" in raw and raw["level"] is not None and type(raw["level"]) is not int:
            _fail(where + "压缩等级类型错误")
    elif kind == "cover":
        if raw["video"] != "":
            _fail(where + "：模板不能包含门面视频路径")
    else:
        key = "size" if kind == "split" else "ext"
        if not isinstance(raw[key], str) or len(raw[key]) > 32:
            _fail(where + "字段类型错误")
    return raw


def _clean_layers(raw) -> list:
    """Reuse the desktop cleaning + layers.validate; cover paths are always blank."""
    from . import formats
    from .desktop.api import Api
    from .layers import LayerSpec, validate
    if not isinstance(raw, list) or not raw:
        _fail("模板至少需要一层")
    if len(raw) > MAX_LAYERS:
        _fail(f"模板最多 {MAX_LAYERS} 层")
    try:
        clean = Api._clean_layers([{k: v for k, v in x.items() if k != "password"} for x in raw])
        for item in clean:
            if item.get("type") == "cover":
                item["video"] = ""
        specs = [LayerSpec.from_dict({**x, "password": None,
                                      **({"video": "template.mp4"} if x.get("type") == "cover" else {})})
                 for x in clean]
        for spec in specs:
            if spec.type == "archive" and spec.fmt not in formats.FORMATS:
                raise ValueError(f"未知格式：{spec.fmt}")
        validate(specs, check_video=False)
    except TemplateError:
        raise
    except Exception as error:
        _fail("层设置无效：" + (str(error)[:120] or type(error).__name__))
    for spec, item in zip(specs, clean):
        if spec.type == "archive" and not formats.get(spec.fmt).supports_password:
            item["locked"] = False
    return clean


def _recipes(raw) -> list:
    from .text_layers import MAX_RECIPES, DeliveryRecipe, validate_recipes
    if not isinstance(raw, list):
        _fail("文案配方结构错误")
    if len(raw) > MAX_RECIPES:
        _fail(f"文案配方最多 {MAX_RECIPES} 个")
    try:
        recipes = validate_recipes([DeliveryRecipe.from_dict(item) for item in raw])
    except Exception:
        _fail("文案配方无效或含未知字段")
    return [recipe.to_dict() for recipe in recipes]


def _options(raw) -> dict:
    _fields(raw, set(), set(OPTION_FIELDS), "打包选项")
    if any(not isinstance(v, bool) for v in raw.values()):
        _fail("打包选项只能是开关")
    return {k: raw[k] for k in OPTION_FIELDS if k in raw}


def _stored_layer(x):
    """Reduce a layer stored by the desktop app to its public fields (drops passwords/paths)."""
    if not isinstance(x, dict) or x.get("type", "archive") not in LAYER_FIELDS:
        return x
    required, optional = LAYER_FIELDS[x.get("type", "archive")]
    out = {k: v for k, v in x.items() if k in required | optional}
    if x.get("type", "archive") == "archive":
        out.setdefault("fmt", x.get("format", "7z"))
        out["locked"] = bool(x.get("locked") or x.get("password"))
        out["header_enc"] = bool(x.get("header_enc", True))
    elif x.get("type") == "cover":
        out["video"] = ""
    return out


def validate_template(raw, *, strict: bool = True) -> dict:
    """Return a clean public template. ``strict=False`` drops fields stored by the
    desktop app (``created``) and blanks cover paths instead of refusing."""
    from .desktop.api import Api
    if not isinstance(raw, dict):
        _fail("模板结构错误")
    if not strict:
        raw = {k: v for k, v in raw.items() if k in TEMPLATE_FIELDS | TEMPLATE_OPTIONAL}
        if isinstance(raw.get("layers"), list):
            raw["layers"] = [_stored_layer(x) for x in raw["layers"]]
    _fields(raw, TEMPLATE_FIELDS, TEMPLATE_OPTIONAL, "模板")
    name = _name(raw["name"])
    if not isinstance(raw["layers"], list):
        _fail("模板层列表结构错误")
    if len(raw["layers"]) > MAX_LAYERS:
        _fail(f"模板最多 {MAX_LAYERS} 层")
    layers = _clean_layers([_layer(x, i) for i, x in enumerate(raw["layers"])])
    disguise, size = raw.get("disguise", ""), raw.get("size", "")
    if not isinstance(disguise, str) or not isinstance(size, str) or len(size) > 32:
        _fail("伪装后缀或分卷大小类型错误")
    try:
        disguise = Api._disguise(disguise)
        if size.strip():
            from .split import parse_size
            parse_size(size.strip())
    except Exception as error:
        _fail(str(error)[:120] or "伪装后缀或分卷大小无效")
    item = {"name": name, "layers": layers, "disguise": disguise, "size": size.strip()}
    if raw.get("options") is not None:
        item["options"] = _options(raw["options"])
    if raw.get("text_recipes") is not None:
        item["text_recipes"] = _recipes(raw["text_recipes"])
    return item


def export_document(items) -> dict:
    """Build the public JSON document from stored templates (ui-templates.json items)."""
    if not isinstance(items, list) or not items:
        _fail("请选择要导出的模板")
    if len(items) > MAX_TEMPLATES:
        _fail(f"最多导出 {MAX_TEMPLATES} 个模板")
    templates = [validate_template(item, strict=False) for item in items]
    names = [t["name"] for t in templates]
    if len(set(names)) != len(names):
        _fail("导出的模板名称重复")
    return {"schema_version": SCHEMA_VERSION, "kind": KIND,
            "exported_at": datetime.now().isoformat(timespec="seconds"), "templates": templates}


def _is_link(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0))


def export_file(items, path) -> dict:
    """Write a new template file; never overwrites an existing file."""
    path = Path(path)
    if path.suffix.lower() != ".json":
        _fail("模板文件必须保存为 .json")
    if _is_link(path.parent) or not path.parent.is_dir():
        _fail("保存位置不存在或是符号链接")
    body = json.dumps(export_document(items), ensure_ascii=False, indent=2) + "\n"
    if len(body.encode("utf-8")) > MAX_FILE_BYTES:
        _fail("模板文件超出大小上限")
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    except FileExistsError:
        _fail("目标文件已存在，不会覆盖")
    return {"path": str(path), "count": len(items)}


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        _fail("模板文件含重复字段")
    return dict(pairs)


def _no_constant(_value):
    _fail("模板文件含非法数值")


def parse_document(text) -> list:
    """Strictly parse template JSON text/bytes into clean templates."""
    if isinstance(text, (bytes, bytearray)):
        if len(text) > MAX_FILE_BYTES:
            _fail("模板文件超出大小上限")
        try:
            text = bytes(text).decode("utf-8-sig")
        except UnicodeDecodeError:
            _fail("模板文件不是 UTF-8 文本")
    if not isinstance(text, str):
        _fail("模板文件结构错误")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        _fail("模板文件超出大小上限")
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except TemplateError:
        raise
    except (ValueError, RecursionError):
        _fail("模板文件不是有效 JSON")
    _fields(data, TOP_FIELDS, TOP_OPTIONAL, "模板文件")
    version = data["schema_version"]
    if type(version) is not int:
        _fail("schema_version 类型错误")
    if version != SCHEMA_VERSION:
        _fail(f"不支持的模板版本：{version}")
    if data["kind"] != KIND:
        _fail("不是密送模板文件")
    if "exported_at" in data and not isinstance(data["exported_at"], str):
        _fail("exported_at 类型错误")
    items = data["templates"]
    if not isinstance(items, list) or not items:
        _fail("模板文件没有模板")
    if len(items) > MAX_TEMPLATES:
        _fail(f"模板文件最多 {MAX_TEMPLATES} 个模板")
    return [validate_template(item) for item in items]


def read_file(path) -> list:
    """Read only the file the user explicitly chose."""
    path = Path(path)
    if path.suffix.lower() != ".json":
        _fail("只能导入 .json 模板文件")
    if _is_link(path):
        _fail("模板文件不能是符号链接")
    try:
        st = os.lstat(path)
    except OSError:
        _fail("模板文件不存在")
    if not stat.S_ISREG(st.st_mode):
        _fail("模板文件必须是普通文件")
    if st.st_size > MAX_FILE_BYTES:
        _fail("模板文件超出大小上限")
    with open(path, "rb") as handle:
        return parse_document(handle.read(MAX_FILE_BYTES + 1))


def unique_name(name: str, taken) -> str:
    folded = {str(n).casefold() for n in taken}
    if name.casefold() not in folded:
        return name
    for n in range(2, 1000):
        suffix = f" ({n})"
        candidate = name[:MAX_NAME - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in folded:
            return candidate
    _fail("无法生成不冲突的模板名称")


def merge(existing, incoming, *, max_templates: int = MAX_TEMPLATES) -> dict:
    """Append validated templates, renaming on conflict. Returns the new list and renames;
    the caller persists ``templates`` (e.g. via Api._save_templates)."""
    existing = [t for t in (existing or []) if isinstance(t, dict) and t.get("name")]
    if len(existing) + len(incoming) > max_templates:
        _fail(f"最多保存 {max_templates} 个模板，请先删除一些")
    taken = [t["name"] for t in existing]
    now = datetime.now().isoformat(timespec="seconds")
    added, renamed = [], []
    for item in incoming:
        name = unique_name(item["name"], taken)
        if name != item["name"]:
            renamed.append({"from": item["name"], "to": name})
        taken.append(name)
        added.append({**item, "name": name, "created": now})
    return {"templates": existing + added, "added": [t["name"] for t in added], "renamed": renamed}


def import_file(path, existing, *, max_templates: int = MAX_TEMPLATES) -> dict:
    return merge(existing, read_file(path), max_templates=max_templates)
