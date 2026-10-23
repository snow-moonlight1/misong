"""Bridge between the desktop web UI and the existing Python workflows.

pywebview exposes every public method to JavaScript, so internal state uses underscore
names. Passwords and the mojibake key stay in memory for one job and are never saved.
"""
from __future__ import annotations

import asyncio
import functools
import json
import os
import queue
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from .. import formats, pack, workflows, preflight
from ..layers import migrate, validate
from ..jobs import save_json
from ..providers import PROVIDERS
from ..publish import Paused, PublishOptions, import_share, prepare, publish
from ..rpa.drivers import PROFILES
from ..rpa.runtime import BROWSERS, DEFAULT_STATE, ROOT, BrowserRuntime
from ..share_options import ACCESS_LABELS, EXPIRY_LABELS, ShareOptions, common_options
from ..sharing import COPY_SCHEMES, encode_copy

RUNS = ROOT / "runs"
SCHEME_LABELS = {"beast": "兽曰", "mojibake": "魔曰", "hajimi": "哈基米", "base64": "Base64",
                 "base64url": "Base64URL", "base32": "Base32", "base85": "Base85", "hex": "Hex",
                 "url": "URL 编码", "reverse": "倒序", "rot13": "ROT13"}
FORMS = {"direct": "直接分享", "simple": "简易中转", "complex": "加密中转"}
SETTING_KEYS = {"layers", "size", "disguise", "raw_merge", "body_disks", "form", "hop_disk", "pwd_hint",
                "expiry", "access", "schemes", "upload_schemes", "pack_split", "pack_size", "checksum", "video", "layers_version"}
BROWSER_LABELS = {"chromium": "Chromium（内置，推荐）", "chrome": "Chrome", "msedge": "Edge"}
ERROR_TYPES = {"DriverBlocked": "网盘页面操作受阻", "TimeoutError": "操作超时", "Error": "浏览器操作出错",
               "RuntimeError": "运行出错", "ValueError": "数据校验失败", "Paused": "已暂停",
               "CancelledError": "已暂停", "OSError": "文件读写失败"}
NET_ERRORS = {"ERR_TIMED_OUT": "连接超时", "ERR_CONNECTION_TIMED_OUT": "连接超时", "ERR_NAME_NOT_RESOLVED": "域名解析失败",
              "ERR_CONNECTION_RESET": "连接被重置", "ERR_CONNECTION_REFUSED": "连接被拒绝", "ERR_CONNECTION_CLOSED": "连接被关闭",
              "ERR_PROXY_CONNECTION_FAILED": "代理连接失败", "ERR_INTERNET_DISCONNECTED": "网络未连接",
              "ERR_ADDRESS_UNREACHABLE": "地址不可达", "ERR_SSL_PROTOCOL_ERROR": "加密连接失败"}
MAX_TEMPLATES = 30
_L = lambda fmt, locked=False: {"fmt": fmt, "locked": locked, "header_enc": True}  # noqa: E731
# Seeded once into ui-templates.json; afterwards they are ordinary templates the owner may rename or delete.
DEFAULT_TEMPLATES = [
    {"name": "lz4 → 7z加密", "layers": [_L("lz4"), _L("7z", True)], "disguise": "", "size": ""},
    {"name": "单层 7z加密", "layers": [_L("7z", True)], "disguise": "", "size": ""},
    {"name": "zip加密", "layers": [_L("zip", True)], "disguise": "", "size": ""},
    {"name": "7z → 7z 双层", "layers": [_L("7z", True), _L("7z", True)], "disguise": "", "size": ""},
]
del _L


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return {"ok": True, "data": fn(self, *args, **kwargs)}
        except (Exception, SystemExit) as e:  # surfaced to the UI as a readable message
            return {"ok": False, "error": str(e) or type(e).__name__}
    return wrapper


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def friendly_error(text: str) -> str:
    """Turn Chromium network failures into a hint the owner can act on."""
    match = re.search(r"net::(ERR_[A-Z_]+)", text or "")
    if not match:
        return text
    host = re.search(r"https?://([^/\s#?]+)", text)
    reason = NET_ERRORS.get(match[1], "网络错误")
    return (f"无法打开 {host[1] if host else '网盘页面'}：{reason}（{match[1]}）。这是电脑到该网站的网络问题，"
            "不是登录或软件配置问题；可检查代理/VPN、DNS 或防火墙后重试。")


def error_text(err) -> str:
    """relay-plan.json stores {type, stage} without the message (it may echo page text)."""
    if not err:
        return ""
    if not isinstance(err, dict):
        return str(err)
    stage = str(err.get("stage") or "")
    where = {"body": "本体上传", "hop": "第一跳上传", "copy": "生成文案", "start": "启动"}.get(stage)
    if where is None and stage.startswith("body-"):
        where = "本体上传 · " + PROVIDERS.get(stage[5:], {}).get("label", stage[5:])
    kind = ERROR_TYPES.get(err.get("type"), err.get("type") or "未知错误")
    return f"{kind}（{where or stage}）" if (where or stage) else kind


def _trash(path: Path) -> None:
    """Move a task folder to the Windows recycle bin so a mistaken delete can be undone."""
    if os.name != "nt":
        shutil.rmtree(path)
        return
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    # FO_DELETE with FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    op = SHFILEOPSTRUCTW(None, 3, str(path) + "\0", None, 0x40 | 0x10 | 0x04 | 0x400, False, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code or op.fAnyOperationsAborted or Path(path).exists():
        raise OSError(f"移到回收站失败（代码 {code}），文件可能正被占用")


def installed_browsers() -> dict:
    """Chromium ships with Playwright; Chrome/Edge are only offered when found on this PC."""
    found = {"chromium": True, "chrome": False, "msedge": False}
    if os.name == "nt":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for key, rel in (("chrome", r"Google\Chrome\Application\chrome.exe"),
                         ("msedge", r"Microsoft\Edge\Application\msedge.exe")):
            found[key] = any(root and (Path(root) / rel).exists() for root in roots)
    else:
        found["chrome"] = bool(shutil.which("google-chrome") or shutil.which("google-chrome-stable"))
        found["msedge"] = bool(shutil.which("microsoft-edge"))
    return found


class Api:
    def __init__(self, runs_dir: Path = RUNS, state_dir: Path = DEFAULT_STATE, runtime_factory=None):
        self._state = Path(state_dir)
        self._default_runs = Path(runs_dir).resolve()
        settings = self._load_settings()
        selected = settings.get("output_dir")
        self._runs = Path(selected).resolve() if isinstance(selected, str) and selected else self._default_runs
        history = settings.get("output_roots")
        self._output_roots = [Path(p).resolve() for p in history if isinstance(p, str) and p] if isinstance(history, list) else []
        self._output_roots = list(dict.fromkeys([self._default_runs, *self._output_roots, self._runs]))
        self._runtime_factory = runtime_factory
        self._events: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._job: dict | None = None
        self._window = None
        self._close_when_idle = False

    # ---------- shell hooks (not exposed) ----------
    def _attach(self, window):
        self._window = window

    def _on_closing(self):
        if self._job is None:
            return True
        self._close_when_idle = True
        self._cancel.set()
        self._emit("toast", level="warn", text="正在暂停当前任务，检查点保存后窗口会自动关闭")
        return False

    def _emit(self, event_type, /, **data):
        self._events.put({"type": event_type, "ts": time.time(), **data})

    def _notify(self, job):
        def notify(text):
            job["step"] = str(text)
            self._emit("log", text=str(text), kind=job["kind"])
        return notify

    def _runtime(self, notify):
        if self._runtime_factory:
            return self._runtime_factory(notify=notify, cancel=self._cancel)
        return BrowserRuntime(state_dir=self._state, notify=notify, cancel=self._cancel)

    def _new_dir(self, kind: str) -> Path:
        return self._runs / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}-{uuid.uuid4().hex[:4]}"

    def _task_folders(self) -> list[Path]:
        folders = []
        for root in self._output_roots:
            if root.is_dir():
                folders.extend(root.iterdir())
        return folders

    def _start(self, kind: str, title: str, work, plan=None) -> dict:
        with self._lock:
            if self._job is not None:
                raise RuntimeError("已有任务在运行，请等待完成或先暂停")
            self._cancel.clear()
            job = {"id": uuid.uuid4().hex[:8], "kind": kind, "title": title,
                   "plan": str(plan) if plan else None, "started": time.time(), "step": "准备中…"}
            self._job = job
        self._emit("job", state="running", job=dict(job))

        def run():
            state, result, error = "done", None, None
            try:
                result = work(job)
            except Paused as e:
                state, error = "paused", str(e)
            except BaseException as e:  # noqa: BLE001 - reported to the UI, job state is checkpointed
                state, error = "error", str(e) or type(e).__name__
                if "net::ERR_" in error:
                    self._emit("log", text=error.splitlines()[0][:300], kind=kind)
                    error = friendly_error(error)
            finally:
                with self._lock:
                    self._job = None
                self._emit("job", state=state, job=dict(job), result=result, error=error)
                if self._close_when_idle and self._window is not None:
                    self._window.destroy()
        threading.Thread(target=run, daemon=True, name=f"nde-{kind}").start()
        return dict(job)

    @staticmethod
    def _layers(raw) -> list[pack.LayerSpec]:
        layers = [pack.LayerSpec.from_dict(item) for item in raw or []]
        for layer, item in zip(layers, raw or []):
            if layer.type == "archive" and layer.fmt not in formats.FORMATS:
                raise ValueError(f"未知格式：{layer.fmt}")
            layer.password = layer.password or None
            layer.header_enc = bool(layer.password) and layer.fmt == "7z" and bool(item.get("header_enc", True))
        validate(layers, check_video=False)
        return layers

    @staticmethod
    def _clean_layers(raw):
        clean = []
        for x in raw or []:
            kind = x.get("type", "archive")
            if kind == "archive":
                item = {"fmt": x.get("fmt", x.get("format", "7z")),
                        "locked": bool(x.get("password") or x.get("locked")),
                        "header_enc": bool(x.get("header_enc", True))}
                if "type" in x:
                    item["type"] = kind
                if x.get("level") is not None:
                    item["level"] = x["level"]
            else:
                key = {"cover": "video", "split": "size", "rename": "ext"}.get(kind)
                if not key:
                    raise ValueError(f"未知层类型：{kind}")
                item = {"type": kind, key: str(x.get(key) or "")}
            clean.append(item)
        return clean

    def _configured_layers(self, cfg, kind):
        specs = self._layers(cfg.get("layers"))
        size = ""
        if cfg.get("layers_version") != 2:
            size = (cfg.get("size") or "1900M") if kind == "pipeline" or cfg.get("split") else ""
        return migrate(specs, disguise=self._disguise(cfg.get("disguise")), video=cfg.get("video"), size=size)

    @_safe
    def preflight_pack(self, cfg, kind="pack"):
        inputs = [Path(p) for p in cfg.get("inputs") or []]
        if not inputs:
            raise ValueError("请先添加资源")
        layers = self._configured_layers(cfg, kind)
        out = Path(cfg.get("out") or self._runs / "pending-pack")
        return preflight.estimate(inputs, layers, out)

    @staticmethod
    def _disguise(value) -> str:
        value = str(value or "").strip().lower()
        if value and not value.startswith("."):
            value = "." + value
        if value and value not in workflows.DISGUISE_EXTS:
            raise ValueError("伪装后缀仅支持：" + " ".join(workflows.DISGUISE_EXTS))
        return value

    @staticmethod
    def _snapshot(cfg, kind: str) -> dict:
        """Settings saved with a task for "用相同设置新建"; passwords are reduced to a locked flag."""
        layers = Api._clean_layers(cfg.get("layers"))
        keys = {"pipeline": ("size", "disguise", "raw_merge", "body_disks", "form", "hop_disk", "pwd_hint",
                             "expiry", "access", "schemes", "checksum", "video", "layers_version", "task_name", "folder_name"),
                "pack": ("size", "split", "disguise", "raw_merge", "checksum", "video", "layers_version"),
                "upload": ("body_disks", "expiry", "access", "schemes", "checksum", "task_name", "folder_name")}[kind]
        snap = {k: cfg[k] for k in keys if k in cfg and not isinstance(cfg[k], dict)}
        if "disguise" in snap:
            snap["disguise"] = Api._disguise(snap["disguise"])
        if kind != "upload":
            snap["layers"] = layers
        return snap

    # ---------- static data ----------
    @_safe
    def bootstrap(self):
        return {
            "formats": [{"key": k, "kind": f.kind, "password": f.supports_password, "ext": f.native_exts[0]}
                        for k, f in formats.FORMATS.items()],
            "providers": [{"key": k, "label": v["label"], "auto": k in PROFILES} for k, v in PROVIDERS.items()],
            "expiry": EXPIRY_LABELS, "access": ACCESS_LABELS, "forms": FORMS, "browsers": list(BROWSERS),
            "browser_labels": BROWSER_LABELS, "browsers_installed": installed_browsers(),
            "disguises": list(workflows.DISGUISE_EXTS), "templates": self._load_templates(),
            "default_templates": [t["name"] for t in DEFAULT_TEMPLATES],
            "schemes": [{"key": s, "label": SCHEME_LABELS.get(s, s)} for s in COPY_SCHEMES],
            "runs": str(self._runs), "settings": self._load_settings(),
            "job": dict(self._job) if self._job else None,
        }

    @_safe
    def share_choices(self, disks):
        expiry, access = common_options(list(disks or []))
        return {"expiry": [{"key": k, "label": EXPIRY_LABELS[k]} for k in expiry],
                "access": [{"key": k, "label": ACCESS_LABELS[k]} for k in access]}

    def _settings_path(self) -> Path:
        return self._state / "ui-settings.json"

    def _load_settings(self) -> dict:
        try:
            return json.loads(self._settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @_safe
    def save_settings(self, data):
        clean = {k: v for k, v in (data or {}).items() if k in SETTING_KEYS}
        if isinstance(clean.get("layers"), list):  # never persist layer passwords
            clean["layers"] = self._clean_layers(clean["layers"])
        merged = {**self._load_settings(), **clean}
        save_json(self._settings_path(), merged)
        return True

    def _set_output_dir(self, folder):
        with self._lock:
            if self._job is not None:
                raise RuntimeError("任务运行中不能更改产物目录，请先暂停")
            if not isinstance(folder, str) or not folder.strip():
                raise ValueError("请选择产物目录")
            target = Path(folder).resolve()
            if not target.is_dir():
                raise ValueError("产物目录不存在或不是文件夹")
            roots = list(dict.fromkeys([*self._output_roots, target]))
            settings = {**self._load_settings(), "output_dir": str(target),
                        "output_roots": [str(p) for p in roots]}
            save_json(self._settings_path(), settings)
            self._runs, self._output_roots = target, roots
        return {"runs": str(target), "changed": True}

    @_safe
    def set_output_dir(self, folder):
        return self._set_output_dir(folder)

    @_safe
    def choose_output_dir(self):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(self._runs))
        return self._set_output_dir(str(result[0])) if result else {"runs": str(self._runs), "changed": False}

    # ---------- custom layer templates (no passwords) ----------
    def _templates_path(self) -> Path:
        return self._state / "ui-templates.json"

    def _load_templates(self) -> list:
        try:
            data = json.loads(self._templates_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        items = [t for t in data.get("templates", []) if isinstance(t, dict) and t.get("name")]
        if not data.get("seeded"):  # first run: built-in shortcuts become normal, removable templates
            names = {t["name"] for t in items}
            items = [json.loads(json.dumps(t)) for t in DEFAULT_TEMPLATES if t["name"] not in names] + items
        return items

    def _save_templates(self, items) -> list:
        save_json(self._templates_path(), {"templates": items, "seeded": True})
        return items

    @_safe
    def templates(self):
        return self._load_templates()

    @_safe
    def save_template(self, name, layers, disguise="", size="", replace=None):
        name = str(name or "").strip()
        if not name or len(name) > 24:
            raise ValueError("模板名称必须为 1–24 个字符")
        specs = self._layers([{**x, "password": None} for x in layers or []])
        clean = self._clean_layers(layers)
        for spec, raw in zip(specs, clean):
            if spec.type == "archive" and not formats.get(spec.fmt).supports_password:
                raw["locked"] = False
        item = {"name": name, "layers": clean, "disguise": self._disguise(disguise),
                "size": str(size or "").strip(), "created": datetime.now().isoformat(timespec="seconds")}
        if item["size"]:
            from ..split import parse_size
            parse_size(item["size"])
        old = str(replace or name)
        items = self._load_templates()
        if replace and name != old and any(t["name"] == name for t in items):
            raise ValueError(f"已有名为「{name}」的模板")
        index = next((i for i, t in enumerate(items) if t["name"] in (old, name)), None)
        if index is None:
            if len(items) >= MAX_TEMPLATES:
                raise ValueError(f"最多保存 {MAX_TEMPLATES} 个模板")
            items.append(item)
        else:  # overwrite / rename in place so chip order stays stable
            items[index] = item
            items = [t for i, t in enumerate(items) if i == index or t["name"] not in (old, name)]
        return self._save_templates(items)

    @_safe
    def delete_template(self, name):
        return self._save_templates([t for t in self._load_templates() if t["name"] != name])

    @_safe
    def reset_templates(self):
        """Bring back deleted built-in shortcuts; the owner's own templates are kept as they are."""
        items = self._load_templates()
        names = {t["name"] for t in items}
        missing = [json.loads(json.dumps(t)) for t in DEFAULT_TEMPLATES if t["name"] not in names]
        if len(items) + len(missing) > MAX_TEMPLATES:
            raise ValueError(f"最多保存 {MAX_TEMPLATES} 个模板，请先删除一些")
        return self._save_templates(missing + items)

    # ---------- files ----------
    @_safe
    def pick_files(self, multiple=True, video=False):
        import webview
        types = ("视频文件 (*.mp4;*.mkv;*.mov)", "所有文件 (*.*)") if video else ()
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=bool(multiple),
                                                 file_types=types)
        return [str(p) for p in (result or [])]

    @_safe
    def pick_folder(self):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return [str(p) for p in (result or [])]

    @_safe
    def describe_paths(self, paths):
        out = []
        for raw in paths or []:
            path = Path(raw)
            if not path.exists():
                continue
            if path.is_dir():
                size = count = 0
                for i, item in enumerate(path.rglob("*")):
                    if item.is_file():
                        size += item.stat().st_size
                        count += 1
                    if i > 50000:
                        break
                out.append({"path": str(path), "name": path.name or str(path), "dir": True, "size": size, "count": count})
            else:
                out.append({"path": str(path), "name": path.name, "dir": False, "size": path.stat().st_size, "count": 1})
        return out

    @_safe
    def folder_files(self, folder):
        return [str(p) for p in sorted(Path(folder).iterdir()) if p.is_file()]

    @_safe
    def open_path(self, path):
        target = Path(path)
        if target == self._runs:
            target.mkdir(parents=True, exist_ok=True)
        while not target.exists() and target != target.parent:
            target = target.parent
        if target.is_file():
            target = target.parent
        os.startfile(str(target))  # Windows desktop app
        return True

    # ---------- jobs ----------
    @_safe
    def poll(self):
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        job = dict(self._job) if self._job else None
        if job and job.get("plan"):
            try:
                job["task"] = self._summary(Path(job["plan"]))
            except (OSError, ValueError, KeyError):
                pass
        return {"events": events, "job": job}

    @_safe
    def pause(self):
        if self._job is None:
            return False
        self._cancel.set()
        self._emit("log", text="正在暂停：当前文件或打包阶段完成后停止，已上传进度会保留", kind=self._job["kind"])
        return True

    @_safe
    def start_pipeline(self, cfg):
        task_name, folder_name = workflows.publication_names(cfg.get("task_name"), cfg.get("folder_name"))
        inputs = [Path(p) for p in cfg.get("inputs") or []]
        if not inputs:
            raise ValueError("请先添加要发布的资源")
        layers = self._configured_layers(cfg, "pipeline")
        disks = tuple(cfg.get("body_disks") or ())
        if not disks:
            raise ValueError("请至少选择一个本体网盘")
        form = cfg.get("form") or "direct"
        if form not in FORMS:
            raise ValueError("未知的分享方式")
        hop = cfg.get("hop_disk") or "feimao"
        share = ShareOptions(cfg.get("expiry") or "default", cfg.get("access") or "default")
        for disk in list(disks) + ([hop] if form != "direct" else []):
            share.validate_disk(disk)
        hop_password = cfg.get("hop_password") or None
        if form == "complex" and not hop_password:
            raise ValueError("加密中转需要填写第一跳压缩包密码")
        schemes = tuple(cfg.get("schemes") or ())
        if not schemes:
            raise ValueError("请至少选择一种链接文案")
        output = self._new_dir("publish")
        checked = preflight.estimate(inputs, layers, output)
        if not checked["ok"]:
            raise ValueError(checked["message"])
        options = PublishOptions(inputs=inputs, out=Path(checked["out"]), layers=layers, size="",
                                 body_disk=disks[0], hop_disk=hop, form=form,
                                 pwd_hint=cfg.get("pwd_hint") or "请向分享者获取解压密码。", schemes=schemes,
                                 share_options=share, body_disks=disks, checksum=bool(cfg.get("checksum")),
                                 task_name=task_name, folder_name=folder_name)
        upload = bool(cfg.get("upload", True))
        key = cfg.get("key") or "ABRACADABRA"
        title = task_name or workflows.title_for(inputs)

        def work(job):
            notify = self._notify(job)
            path = prepare(options, notify)
            workflows.update_meta(path.parent, settings=self._snapshot(cfg, "pipeline"))
            job["plan"] = str(path)
            if not upload:
                return {"plan": str(path), "task": self._summary(path)}
            result = asyncio.run(publish(path, runtime=self._runtime(notify), notify=notify, cancel=self._cancel,
                                         key=key, hop_password=hop_password))
            return {"plan": str(path), "copies": result["copies"], "task": self._summary(path)}
        return self._start("pipeline", title, work)

    @_safe
    def start_pack(self, cfg):
        inputs = [Path(p) for p in cfg.get("inputs") or []]
        if not inputs:
            raise ValueError("请先添加要打包的资源")
        layers = self._configured_layers(cfg, "pack")
        out = Path(cfg["out"]) if cfg.get("out") else self._new_dir("pack")
        checked = preflight.estimate(inputs, layers, out)
        if not checked["ok"]:
            raise ValueError(checked["message"])
        out = Path(checked["out"])

        def work(job):
            result = workflows.pack_only(inputs, layers, out, checksum=bool(cfg.get("checksum")),
                                         notify=self._notify(job))
            workflows.update_meta(Path(result["out"]), settings=self._snapshot(cfg, "pack"))
            return result
        return self._start("pack", workflows.title_for(inputs), work)

    @_safe
    def start_upload(self, cfg):
        task_name, folder_name = workflows.publication_names(cfg.get("task_name"), cfg.get("folder_name"))
        files = [Path(p) for p in cfg.get("files") or []]
        disks = tuple(cfg.get("body_disks") or ())
        share = ShareOptions(cfg.get("expiry") or "default", cfg.get("access") or "default")
        schemes = tuple(cfg.get("schemes") or ())
        key = cfg.get("key") or "ABRACADABRA"
        if not files:
            raise ValueError("请先添加要上传的文件")
        if not disks:
            raise ValueError("请至少选择一个网盘")
        for disk in disks:
            share.validate_disk(disk)
        out = self._new_dir("upload")

        def work(job):
            notify = self._notify(job)
            path = workflows.prepare_upload(files, out, disks, share, schemes, notify, checksum=bool(cfg.get("checksum")),
                                            task_name=task_name, folder_name=folder_name)
            workflows.update_meta(path.parent, settings=self._snapshot(cfg, "upload"))
            job["plan"] = str(path)
            result = asyncio.run(publish(path, runtime=self._runtime(notify), notify=notify, cancel=self._cancel, key=key))
            return {"plan": str(path), "copies": result["copies"], "task": self._summary(path)}
        return self._start("upload", task_name or workflows.title_for(files), work)

    @_safe
    def resume_task(self, plan, key="", hop_password=""):
        path = Path(plan)
        summary = self._summary(path)
        if summary["state"] == "complete":
            raise ValueError("该任务已经完成")

        def work(job):
            notify = self._notify(job)
            result = asyncio.run(publish(path, runtime=self._runtime(notify), notify=notify, cancel=self._cancel,
                                         key=key or "ABRACADABRA", hop_password=hop_password or None))
            return {"plan": str(path), "copies": result["copies"], "task": self._summary(path)}
        return self._start(summary["kind"], summary["title"], work, plan=path)

    # ---------- tasks ----------
    @staticmethod
    def _derived_settings(plan: dict, stages: list, kind: str) -> dict:
        """Best-effort settings for tasks created before snapshots were stored."""
        opts = plan.get("share_options") or {}
        snap = {"body_disks": [s["disk"] for s in stages if s["role"] == "body"], "schemes": plan.get("schemes", []),
                "expiry": opts.get("expiry", "default"), "access": opts.get("access", "default")}
        if kind == "pipeline":
            hop = next((s["disk"] for s in stages if s["role"] == "hop"), None)
            snap.update(form=plan.get("form", "direct"), pwd_hint=plan.get("pwd_hint", ""), **({"hop_disk": hop} if hop else {}))
        return snap

    def _extras_path(self) -> Path:
        return self._state / "ui-tasks.json"

    def _extras(self) -> list[str]:
        try:
            data = json.loads(self._extras_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [str(x) for x in data.get("extra", []) if isinstance(x, str)]

    def _save_extras(self, items) -> None:
        save_json(self._extras_path(), {"extra": list(dict.fromkeys(items))})

    def _decorate(self, data: dict, meta: dict, folder: Path) -> dict:
        data["starred"] = bool(meta.get("starred"))
        data["note"] = str(meta.get("note") or "")
        data["imported"] = folder.resolve().parent not in self._output_roots
        return data

    def _summary(self, path: Path) -> dict:
        path = Path(path)
        plan = json.loads(path.read_text(encoding="utf-8"))
        meta = workflows.read_meta(path.parent)
        stages = []
        for stage in plan.get("stages", []):
            disk = stage.get("disk", "")
            stages.append({"id": stage["id"], "role": "hop" if stage["id"] == "hop" else "body", "disk": disk,
                           "label": PROVIDERS.get(disk, {}).get("label", disk), "state": stage.get("state", "pending"),
                           "done": len(stage.get("uploaded", {})), "total": len(stage.get("files", [])),
                           "share": stage.get("share")})
        stages.sort(key=lambda s: s["role"] == "hop")
        stat = path.stat()
        kind = meta.get("kind") or ("pipeline" if plan.get("pwd_hint") else "upload")
        data = {"plan": str(path), "dir": str(path.parent), "id": plan.get("id"),
                "kind": kind, "title": meta.get("title") or path.parent.name,
                "created": meta.get("created") or _iso(path.parent.stat().st_ctime), "updated": _iso(stat.st_mtime),
                "state": plan.get("state", "prepared"), "form": plan.get("form", "direct"),
                "schemes": plan.get("schemes", []), "share_options": plan.get("share_options", {}),
                "stages": stages, "error": error_text(plan.get("error")),
                "settings": meta.get("settings") or self._derived_settings(plan, stages, kind)}
        return self._decorate(data, meta, path.parent)

    def _pack_summary(self, folder: Path) -> dict:
        meta = workflows.read_meta(folder)
        chain = meta.get("chain", "")
        settings = meta.get("settings") or {"layers": [{"fmt": f, "locked": False, "header_enc": True}
                                                       for f in reversed(chain.split(",")) if f]}
        data = {"plan": None, "dir": str(folder), "kind": "pack", "title": meta.get("title") or folder.name,
                "created": meta.get("created") or _iso(folder.stat().st_ctime), "state": "complete", "error": "",
                "chain": chain, "artifact": meta.get("artifact", ""), "stages": [], "settings": settings}
        return self._decorate(data, meta, folder)

    def _task_at(self, folder: Path) -> dict | None:
        if (folder / "relay-plan.json").exists():
            return self._summary(folder / "relay-plan.json")
        if workflows.read_meta(folder).get("kind") == "pack":
            return self._pack_summary(folder)
        return None

    @_safe
    def list_tasks(self):
        items, seen = [], set()
        folders = self._task_folders()
        for folder in folders + [Path(p) for p in self._extras()]:
            key = str(folder.resolve()).casefold()
            if key in seen or not folder.is_dir():
                continue
            seen.add(key)
            try:
                task = self._task_at(folder)
            except (OSError, ValueError, KeyError):
                continue
            if task:
                items.append(task)
        items.sort(key=lambda x: x["created"], reverse=True)
        return items

    def _managed(self, folder) -> Path:
        """Only tasks under remembered output roots or explicitly imported may be managed."""
        folder = Path(folder).resolve()
        extras = {str(Path(p).resolve()).casefold() for p in self._extras()}
        if folder.parent not in self._output_roots and str(folder).casefold() not in extras:
            raise ValueError("只能管理任务中心里的任务文件夹")
        if not folder.is_dir():
            raise ValueError("任务文件夹不存在")
        return folder

    @_safe
    def update_task(self, folder, changes):
        folder = self._managed(folder)
        task = self._task_at(folder)
        if task is None:
            raise ValueError("该文件夹不是任务")
        clean = {}
        if "title" in changes:
            title = str(changes["title"] or "").strip()
            if not title or len(title) > 120:
                raise ValueError("任务名称需为 1–120 个字符")
            clean["title"] = title
        if "starred" in changes:
            clean["starred"] = bool(changes["starred"])
        if "note" in changes:
            note = str(changes["note"] or "").strip()
            if len(note) > 500:
                raise ValueError("备注最多 500 个字符")
            clean["note"] = note
        if not workflows.read_meta(folder):
            clean = {"kind": task["kind"], "title": task["title"], "created": task["created"], **clean}
        workflows.update_meta(folder, **clean)
        return self._task_at(folder)

    @_safe
    def delete_task(self, folder):
        folder = self._managed(folder)
        job = self._job
        if job and job.get("plan") and Path(job["plan"]).resolve().parent == folder:
            raise RuntimeError("该任务正在运行，请先暂停")
        extras = self._extras()
        imported = [p for p in extras if str(Path(p).resolve()).casefold() == str(folder).casefold()]
        if imported:  # imported folders belong to the owner: only forget them, keep the files
            self._save_extras([p for p in extras if p not in imported])
            return {"removed": str(folder), "trashed": False}
        _trash(folder)
        return {"removed": str(folder), "trashed": True}

    @_safe
    def import_task(self, folder):
        folder = Path(folder or "").resolve()
        if not str(folder) or not folder.is_dir():
            raise ValueError("请选择任务文件夹")
        if not (folder / "relay-plan.json").exists() and workflows.read_meta(folder).get("kind") != "pack":
            sidecars = sorted(folder.glob("*.nde.json"))
            if not sidecars:
                raise ValueError("该文件夹里没有 relay-plan.json、nde-task.json 或 *.nde.json，无法识别为任务")
            artifact = folder / sidecars[0].name[:-len(".nde.json")]
            info = {}
            try:
                info = json.loads(sidecars[0].read_text(encoding="utf-8"))
                records = [x for x in info.get("layers") or [] if isinstance(x, dict)]  # outermost first
            except (OSError, ValueError, AttributeError):
                records = []
            chain = ",".join(str(x.get("format", x.get("type", ""))) for x in records)
            if info.get("version") == 2 and info.get("artifacts"):
                artifact = folder / info["artifacts"][0]["name"]
            layers = self._clean_layers([{**r, "fmt": r.get("format", "7z")} for r in reversed(records)])
            workflows.write_meta(folder, "pack", folder.name, chain=chain, artifact=str(artifact),
                                 **({"settings": {"layers": layers, "layers_version": 2}} if layers else {}))
        if folder.parent not in self._output_roots:
            self._save_extras(self._extras() + [str(folder)])
        return self._task_at(folder)

    @_safe
    def task_detail(self, plan=None, folder=None):
        if plan:
            path = Path(plan)
            data = self._summary(path)
            copy_dir = path.parent / "copy"
            data["copies"] = {s: (copy_dir / f"{s}.txt").read_text(encoding="utf-8").rstrip("\n")
                              for s in data["schemes"] if (copy_dir / f"{s}.txt").exists()}
            plain = copy_dir / "share-plain.txt"
            data["plain"] = plain.read_text(encoding="utf-8").rstrip("\n") if plain.exists() else ""
            raw = json.loads(path.read_text(encoding="utf-8"))
            body = next((s for s in raw.get("stages", []) if s["id"] == "body"), {})
            data["files"] = [{"name": Path(r["path"]).name, "size": r["size"], "path": r["path"]} for r in body.get("files", [])]
            return data
        folder = Path(folder)
        data = self._pack_summary(folder)
        data["files"] = [{"name": str(p.relative_to(folder)), "size": p.stat().st_size, "path": str(p)}
                         for p in sorted(folder.rglob("*")) if p.is_file() and p.name != workflows.META_NAME]
        return data

    @_safe
    def import_share(self, plan, stage_id, text):
        if self._job is not None:
            raise RuntimeError("请先暂停正在运行的任务再回填")
        import_share(Path(plan), stage_id, text or "")
        return self._summary(Path(plan))

    # ---------- codec ----------
    @_safe
    def encode(self, text, schemes, key=""):
        if not text:
            raise ValueError("请输入要加密的文本")
        return encode_copy(text, list(schemes), key=key or "ABRACADABRA")

    @_safe
    def decode(self, text, scheme, key=""):
        from ..encoders import beast, hajimi, mojibake, plain
        text = (text or "").strip()
        if not text:
            raise ValueError("请输入要解密的密文")
        if scheme == "beast":
            return beast.decode(text, dialect="auto")
        if scheme == "hajimi":
            return hajimi.decode(text)
        if scheme == "mojibake":
            return mojibake.decode(text, key=key or "ABRACADABRA")
        return plain.decode(scheme, text)

    # ---------- accounts ----------
    def _history_verified(self) -> dict:
        """Latest automatic upload+share per disk found in task history.

        Older status files were overwritten by probes and lost the fact that a disk once worked;
        a stage that was uploaded completely and shared by the driver (not a hand-filled link) proves it.
        """
        found = {}
        folders = self._task_folders()
        for folder in folders + [Path(p) for p in self._extras()]:
            path = Path(folder) / "relay-plan.json"
            try:
                if not path.is_file():
                    continue
                plan = json.loads(path.read_text(encoding="utf-8"))
                when = _iso(path.stat().st_mtime)
            except (OSError, ValueError):
                continue
            for stage in plan.get("stages", []) if isinstance(plan, dict) else []:
                if not isinstance(stage, dict) or stage.get("manual") or stage.get("state") != "shared":
                    continue
                share, files = stage.get("share"), stage.get("files") or []
                if (isinstance(share, dict) and share.get("url") and files
                        and len(stage.get("uploaded") or {}) >= len(files)):
                    disk = str(stage.get("disk") or "")
                    if disk and when > found.get(disk, ""):
                        found[disk] = when
        return found

    @_safe
    def accounts(self):
        """One owner-facing state per disk, derived from the login session and the driver history.

        ``state``: none (未登录) · loggedin (已登录 · 未测试) · tested (已通过测试) ·
        expired (登录失效) · neterr (检测失败：网络). A later 检测登录 never downgrades ``tested``.
        """
        result = []
        history = self._history_verified()
        for disk, provider in PROVIDERS.items():
            auto = disk in PROFILES
            info = {"status": "unimplemented"}
            if auto:
                status_file = self._state / f"{disk}-status.json"
                try:
                    info = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}
                except (ValueError, OSError):
                    info = {}
                info = info if isinstance(info, dict) else {}
                info.setdefault("status", "probe")
            browser = BrowserRuntime(state_dir=self._state).browser_for(disk) if auto else "chromium"
            session_file = self._state / f"{disk}.json"
            verified_at = max(str(info.get("verified_at") or ""), history.get(disk, "") if auto else "")
            verified = bool(verified_at) or info["status"] == "ready"
            raw_error = str(info.get("last_error") or "")
            net_error = "net::ERR_" in raw_error
            session = session_file.exists()
            if not auto:
                state = "manual"
            elif session and info.get("session_error"):
                state = "neterr" if net_error else "expired"
            elif not session:
                state = "none"
            else:
                state = "tested" if verified else "loggedin"
            result.append({"key": disk, "label": provider["label"], "auto": auto, "status": info["status"],
                           "state": state, "verified": verified, "verified_at": verified_at,
                           "session": session,
                           "session_saved": _iso(session_file.stat().st_mtime) if session_file.exists() else "",
                           "session_at": info.get("session_at", ""), "session_error": bool(info.get("session_error")),
                           "last_error": friendly_error(raw_error), "net_error": net_error,
                           "last_error_at": info.get("last_error_at", ""), "browser": browser})
        return result

    @_safe
    def account_action(self, disk, op, browser=None):
        if op not in ("login", "probe") or disk not in PROFILES:
            raise ValueError("该网盘暂不支持此操作")
        label = PROVIDERS[disk]["label"]

        def work(job):
            runtime = BrowserRuntime(state_dir=self._state, notify=self._notify(job), cancel=self._cancel,
                                     browser_channel=browser or None)
            asyncio.run(getattr(runtime, op)(disk))
            return {"disk": disk, "op": op}
        return self._start("account", ("登录 " if op == "login" else "检测登录 ") + label, work)
