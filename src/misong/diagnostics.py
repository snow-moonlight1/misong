"""Diagnostic bundle export (roadmap v0.2 item 7).

The bundle is a ZIP built only from an explicit whitelist of members that this
module *generates*; it never walks ``rpa/state``, ``runs`` or ``tmp``. It reads
exactly these files, each checked to be a regular non-link file inside its root:

* ``<state>/<disk>-status.json`` for the known provider keys (whitelisted fields);
* public health caches ``<state>/checks|selfchecks/<disk>.json`` (fixed fields);
* the *names and sizes* of ``<state>/failures/<disk>/page.png|page.html``
  and those fixed filenames in bounded ``check-<12 hex>`` child folders
  (a listing only, never the content: HTML and screenshots may show account data);
* ``misong-task.json`` / ``nde-task.json`` / ``relay-plan.json`` of task folders
  the caller explicitly selected (reduced to a whitelisted public summary);
* screenshots only when the caller passes files the user picked this time.

Sessions, cookies, sessionStorage, browser profiles, ``.mskey`` / ``.tkey``,
source or intermediate copy text and passwords are never read into the bundle.
Every generated string goes through literal scrubbing of caller-supplied
secrets and data-directory paths, then :func:`misong.redact.redact_data`.
Screenshots are binary and are NOT text-redacted; callers must show
``SCREENSHOT_NOTICE`` to the user.
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import stat
from itertools import islice
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .redact import PLACEHOLDER, redact_data

SCHEMA_VERSION = 1
MAX_TASKS = 20
MAX_SCREENSHOTS = 8
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_LOG_LINES = 2000
MAX_LOG_CHARS = 400_000
MAX_MEMBERS = 64
MAX_TOTAL_BYTES = 40 * 1024 * 1024
SCREENSHOT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
PROTECTED_SUFFIXES = (".mskey", ".tkey")
TASK_FILES = ("misong-task.json", "nde-task.json")
PLAN_FILE = "relay-plan.json"
FAILURE_FILES = ("page.png", "page.html")
STATUS_FIELDS = ("status", "verified_at", "session_at", "session_error", "last_error", "last_error_at")
SETTING_FIELDS = ("form", "body_disks", "hop_disk", "expiry", "access", "schemes", "layers_version",
                  "checksum", "raw_merge", "size", "disguise", "split", "cleanup_after_upload")
LAYER_FIELDS = ("type", "fmt", "locked", "header_enc", "level", "size", "ext")
SCREENSHOT_NOTICE = ("已附加截图：截图是图片，未经过文本脱敏，可能显示账号、文件名、分享链接或提取码。"
                     "发送诊断包前请逐张确认。")
EXCLUDED = ("登录状态/Cookie/sessionStorage/浏览器资料", ".mskey/.tkey 钥匙", "文案原文与中间文案",
            "各层密码与魔曰密钥", "失败快照 HTML 与截图内容（仅列清单）", "runs/state/tmp 的其他文件")


class DiagnosticsError(ValueError):
    """Export refused; nothing was written (or the partial file was removed)."""


# ---------------------------------------------------------------- file guards
def _is_link(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_reparse_tag", 0))  # Windows junctions / reparse points


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _regular(path: Path, root: Path | None = None) -> bool:
    if _is_link(path) or (root is not None and (_is_link(root) or not _inside(path, root))):
        return False
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def _read_json(path: Path, root: Path):
    """Return (data, problem). Never raises for broken records."""
    if not path.exists() and not _is_link(path):
        return None, "missing"
    if not _regular(path, root):
        return None, "rejected_link_or_outside"
    try:
        if path.stat().st_size > MAX_RECORD_BYTES:
            return None, "too_large"
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None, "corrupt"


# ---------------------------------------------------------------- scrubbing
class _Scrubber:
    """Literal secrets and private paths first, then the shared redact rules."""

    def __init__(self, secrets=(), paths=()):
        self.secrets = sorted({s for s in secrets if isinstance(s, str) and len(s) >= 3}, key=len, reverse=True)
        patterns = []
        for label, raw in paths:
            if not raw:
                continue
            parts = [p for p in re.split(r"[\\/]+", str(raw)) if p]
            if len(parts) < 2:
                continue
            lead = r"[\\/]*" if str(raw)[:1] in "\\/" else ""
            patterns.append((len(str(raw)), re.compile(lead + r"[\\/]+".join(map(re.escape, parts)), re.I), label))
        self.paths = [(rx, label) for _, rx, label in sorted(patterns, key=lambda x: x[0], reverse=True)]

    def text(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, PLACEHOLDER)
        for rx, label in self.paths:
            value = rx.sub(lambda _m, label=label: label, value)
        return value

    def _pre(self, value):
        if isinstance(value, dict):
            return {self.text(k) if isinstance(k, str) else k: self._pre(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._pre(v) for v in value]
        if isinstance(value, Path):
            return self.text(str(value))
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, (bytes, bytearray)):
            return PLACEHOLDER
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self.text(str(value))

    def data(self, value):
        return redact_data(self._pre(value))


def _private_paths(state_dir, task_dirs, extra=()) -> list[tuple[str, str]]:
    from .paths import resolve_paths
    found = []
    try:
        resolved = resolve_paths()
        found += [("<MISONG_HOME>", str(resolved.home)), ("<STATE>", str(resolved.state)),
                  ("<RUNS>", str(resolved.runs))]
    except Exception:
        pass
    if state_dir is not None:
        found += [("<STATE>", str(Path(state_dir))), ("<STATE>", str(Path(state_dir).resolve()))]
    for i, folder in enumerate(task_dirs, 1):
        found += [(f"<TASK-{i}>", str(Path(folder))), (f"<TASK-{i}>", str(Path(folder).resolve()))]
    for label, raw in extra:
        found.append((label, str(raw)))
    try:
        found.append(("<USER_HOME>", str(Path.home())))
    except Exception:
        pass
    return found


# ---------------------------------------------------------------- summaries
def _layers(raw) -> list:
    if not isinstance(raw, list):
        return []
    return [{k: x[k] for k in LAYER_FIELDS if k in x and isinstance(x[k], (str, bool, int, type(None)))}
            for x in raw[:64] if isinstance(x, dict)]


def _settings(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {k: raw[k] for k in SETTING_FIELDS if k in raw and not isinstance(raw[k], dict)}
    if "layers" in raw:
        out["layers"] = _layers(raw["layers"])
    return out


def _stage(raw) -> dict:
    if not isinstance(raw, dict):
        return {"corrupt": True}
    files = raw.get("files") if isinstance(raw.get("files"), list) else []
    total = sum(f.get("size", 0) for f in files if isinstance(f, dict) and isinstance(f.get("size"), int))
    error = raw.get("error")
    return {"id": str(raw.get("id", "")), "role": str(raw.get("role", "")), "disk": str(raw.get("disk", "")),
            "state": str(raw.get("state", "")), "file_count": len(files), "total_bytes": total,
            "uploaded_count": len(raw["uploaded"]) if isinstance(raw.get("uploaded"), (dict, list)) else 0,
            "shared": bool(raw.get("share")), "custom_folder": bool(raw.get("custom_folder")),
            "error": ({"type": str(error.get("type", "")), "stage": str(error.get("stage", ""))}
                      if isinstance(error, dict) else ("present" if error else None))}


def _delivery(plan: dict):
    try:
        from .workflows import delivery_status
        stages = plan.get("stages") if isinstance(plan.get("stages"), list) else []
        status = delivery_status({**plan, "stages": [s for s in stages if isinstance(s, dict)]})
    except Exception:
        return {"corrupt": True}
    return {"mode": status.get("mode"), "label": status.get("label"),
            "share_complete": bool(status.get("share_complete")),
            "delivery_complete": bool(status.get("delivery_complete")),
            "recipes": [{"recipe_id": r.get("recipe_id"), "status": r.get("status"),
                         "error_code": r.get("error_code"),
                         "artifact_roles": [f.get("role") for f in r.get("files", [])]}
                        for r in status.get("recipes", [])]}


def _recipes(raw) -> list:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:32]:
        if not isinstance(item, dict):
            out.append({"corrupt": True})
            continue
        layers = item.get("layers") if isinstance(item.get("layers"), list) else []
        carrier = item.get("carrier") if isinstance(item.get("carrier"), dict) else {}
        out.append({"id": str(item.get("id", "")), "name": str(item.get("name", "")),
                    "schemes": [str(x.get("scheme", "")) for x in layers if isinstance(x, dict)],
                    "secret_slots": sum(1 for x in layers if isinstance(x, dict) and x.get("secret_slot"))
                    + (1 if carrier.get("secret_slot") else 0),
                    "carrier": str(carrier.get("format_id", ""))})
    return out


def task_summary(folder) -> dict:
    """Whitelisted public summary of one explicitly selected task folder."""
    folder = Path(folder)
    if _is_link(folder) or not folder.is_dir():
        return {"folder": folder.name, "problem": "not_a_task_folder"}
    summary: dict = {"folder": folder.name, "problems": []}
    meta, problem = None, "missing"
    for name in TASK_FILES:
        meta, problem = _read_json(folder / name, folder)
        if problem != "missing":
            break
    if problem and problem != "missing":
        summary["problems"].append("task:" + problem)
    if isinstance(meta, dict):
        summary["task"] = {k: meta[k] for k in ("kind", "title", "created", "chain", "folder_name")
                           if isinstance(meta.get(k), str)}
        summary["task"]["settings"] = _settings(meta.get("settings"))
    elif meta is not None:
        summary["problems"].append("task:corrupt")
    plan, problem = _read_json(folder / PLAN_FILE, folder)
    if problem and problem != "missing":
        summary["problems"].append("plan:" + problem)
    if isinstance(plan, dict):
        stages = plan.get("stages")
        error = plan.get("error")
        summary["plan"] = {
            "version": plan.get("version") if isinstance(plan.get("version"), int) else None,
            "form": str(plan.get("form", "")), "state": str(plan.get("state", "")),
            "share_options": {k: str(v) for k, v in plan["share_options"].items() if k in ("expiry", "access")}
            if isinstance(plan.get("share_options"), dict) else {},
            "schemes": [str(s) for s in plan.get("schemes", []) if isinstance(s, str)]
            if isinstance(plan.get("schemes"), list) else [],
            "stages": [_stage(s) for s in stages[:32]] if isinstance(stages, list) else [{"corrupt": True}],
            "error": ({"type": str(error.get("type", "")), "stage": str(error.get("stage", ""))}
                      if isinstance(error, dict) else ("present" if error else None)),
            "text_recipes": _recipes(plan.get("text_recipes")),
            "delivery": _delivery(plan),
        }
    elif plan is not None:
        summary["problems"].append("plan:corrupt")
    return summary


def account_status(state_dir) -> dict:
    from .providers import PROVIDERS
    state = Path(state_dir)
    out = {}
    for disk in PROVIDERS:
        data, problem = _read_json(state / f"{disk}-status.json", state)
        item = ({k: data[k] for k in STATUS_FIELDS if k in data and not isinstance(data[k], (dict, list))}
                if isinstance(data, dict) else {} if problem == "missing" else {"problem": problem or "corrupt"})
        for directory, label in (("checks", "check"), ("selfchecks", "selfcheck")):
            report, _ = _read_json(state / directory / (disk + ".json"), state)
            if isinstance(report, dict):
                public = {k: report[k] for k in ("status", "code", "checked_at", "attempts", "headless")
                          if k in report and isinstance(report[k], (str, int, bool))}
                if label == "selfcheck" and isinstance(report.get("selectors"), list):
                    public["selectors"] = [{k: r[k] for k in ("item", "status") if k in r and isinstance(r[k], str)}
                                           for r in report["selectors"][:30] if isinstance(r, dict)]
                item[label] = public
        if item:
            out[disk] = item
    return out


def failure_listing(state_dir) -> list:
    """Names/sizes of local failure snapshots; their content is never bundled."""
    from .providers import PROVIDERS
    root = Path(state_dir) / "failures"
    if _is_link(root) or not root.is_dir():
        return []
    listing = []
    for disk in PROVIDERS:
        folder = root / disk
        if _is_link(folder) or not folder.is_dir():
            continue
        snapshots = [folder]
        snapshots += [p for p in islice(folder.iterdir(), 200)
                      if re.fullmatch(r"check-[0-9a-f]{12}", p.name)
                      and not _is_link(p) and p.is_dir()][:30]
        for snapshot in snapshots:
            for name in FAILURE_FILES:
                path = snapshot / name
                if _regular(path, root):
                    st = path.stat()
                    listing.append({"disk": disk, "file": (snapshot.name + "/" if snapshot != folder else "") + name,
                                    "bytes": st.st_size,
                                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                                    "included": False})
    return listing


def _version_info() -> dict:
    return {"misong": __version__, "python": platform.python_version(),
            "implementation": platform.python_implementation(), "system": platform.system(),
            "release": platform.release(), "machine": platform.machine(),
            "frozen": bool(getattr(sys, "frozen", False))}


def _environment(environment):
    if environment is not None:
        return environment
    try:
        from .doctor import check_environment
        return check_environment()
    except Exception as error:  # the bundle must still be produced
        return {"ok": False, "error": type(error).__name__}


def _logs(lines) -> str:
    out, total = [], 0
    for line in list(lines or [])[-MAX_LOG_LINES:]:
        text = line if isinstance(line, str) else json.dumps(line, ensure_ascii=False, default=str)
        text = text.replace("\r", " ")[:2000]
        total += len(text)
        if total > MAX_LOG_CHARS:
            out.append("[truncated]")
            break
        out.append(text)
    return "\n".join(out)


def _screenshots(paths) -> list[tuple[str, Path]]:
    picked = []
    for raw in list(paths or []):
        path = Path(raw)
        name = path.name.lower()
        if name.endswith(PROTECTED_SUFFIXES):
            raise DiagnosticsError("钥匙文件不能放入诊断包")
        if not name.endswith(SCREENSHOT_SUFFIXES):
            raise DiagnosticsError("截图只接受 png/jpg/webp 图片")
        if not _regular(path):
            raise DiagnosticsError("截图必须是普通文件，不能是符号链接或目录")
        if path.stat().st_size > MAX_SCREENSHOT_BYTES:
            raise DiagnosticsError("单张截图过大")
        picked.append((f"screenshots/{len(picked) + 1:02d}{path.suffix.lower()}", path))
    if len(picked) > MAX_SCREENSHOTS:
        raise DiagnosticsError(f"最多附加 {MAX_SCREENSHOTS} 张截图")
    return picked


def _dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")


def build_members(*, tasks=(), state_dir=None, log_lines=(), secrets=(), environment=None,
                  extra_paths=()) -> dict[str, bytes]:
    """Generate the text members (already scrubbed). Pure apart from whitelisted reads."""
    tasks = [Path(t) for t in tasks or []]
    if len(tasks) > MAX_TASKS:
        raise DiagnosticsError(f"一次最多选择 {MAX_TASKS} 个任务")
    scrub = _Scrubber(secrets, _private_paths(state_dir, tasks, extra_paths))
    members = {
        "version.json": _dump(scrub.data(_version_info())),
        "environment.json": _dump(scrub.data(_environment(environment))),
        "logs.txt": scrub.data(_logs(log_lines)).encode("utf-8"),
    }
    if state_dir is not None:
        members["accounts.json"] = _dump(scrub.data(account_status(state_dir)))
        members["failures.json"] = _dump(scrub.data(failure_listing(state_dir)))
    for i, folder in enumerate(tasks, 1):
        members[f"tasks/task-{i:02d}.json"] = _dump(scrub.data(task_summary(folder)))
    return members


def export_diagnostics(output, *, tasks=(), state_dir=None, log_lines=(), screenshots=(), secrets=(),
                       environment=None, extra_paths=()) -> dict:
    """Write a new diagnostic ZIP at ``output``; refuses to overwrite.

    ``secrets`` are values currently in memory (passwords, 魔曰 keys, share codes)
    to scrub literally in addition to the pattern rules; they are never written.
    Returns ``{path, members, bytes, screenshots, notice}``.
    """
    output = Path(output)
    if output.suffix.lower() != ".zip":
        raise DiagnosticsError("诊断包必须保存为 .zip")
    if output.exists() or _is_link(output):
        raise DiagnosticsError("目标文件已存在，不会覆盖")
    parent = output.parent
    if _is_link(parent) or not parent.is_dir():
        raise DiagnosticsError("保存位置不存在或是符号链接")
    shots = _screenshots(screenshots)
    members = build_members(tasks=tasks, state_dir=state_dir, log_lines=log_lines, secrets=secrets,
                            environment=environment, extra_paths=extra_paths)
    leaked = [s for s in secrets if isinstance(s, str) and len(s) >= 3
              and any(s.encode("utf-8") in body for body in members.values())]
    if leaked:  # defence in depth; should be unreachable
        raise DiagnosticsError("脱敏自检失败，已停止导出")
    names = list(members) + [name for name, _ in shots]
    manifest = {"schema_version": SCHEMA_VERSION, "created": datetime.now().isoformat(timespec="seconds"),
                "members": names + ["manifest.json"], "excluded": list(EXCLUDED),
                "screenshots": {"count": len(shots), "text_redacted": False} if shots else {"count": 0}}
    members["manifest.json"] = _dump(manifest)
    if len(members) + len(shots) > MAX_MEMBERS:
        raise DiagnosticsError("诊断包文件数超出上限")
    total = sum(len(b) for b in members.values()) + sum(p.stat().st_size for _, p in shots)
    if total > MAX_TOTAL_BYTES:
        raise DiagnosticsError("诊断包体积超出上限")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
        for name, path in shots:
            if not _regular(path):
                raise DiagnosticsError("截图在导出过程中被替换")
            data = path.read_bytes()
            if len(data) > MAX_SCREENSHOT_BYTES:
                raise DiagnosticsError("单张截图过大")
            archive.writestr(name, data)
    try:
        with open(output, "xb") as handle:
            handle.write(buffer.getvalue())
    except FileExistsError as error:
        raise DiagnosticsError("目标文件已存在，不会覆盖") from error
    except OSError:
        try:
            output.unlink()
        except OSError:
            pass
        raise
    return {"path": str(output), "members": sorted(members) + [n for n, _ in shots],
            "bytes": output.stat().st_size, "screenshots": len(shots),
            "notice": SCREENSHOT_NOTICE if shots else ""}
