"""Read-only environment checks for the first level of ``misong doctor``.

Nothing here logs in, opens a browser, touches a netdisk, downloads anything or
writes settings. Probe messages never contain executable paths, environment
values or raw command output; only parsed version numbers are reported.

``check_environment()`` always returns a report, even when a dependency is
missing or a probe times out. Required failures set ``ok`` to false; missing
optional tooling (魔曰 / web upload / desktop) only produces warnings.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 11)
MIN_NODE = 18
PROBE_TIMEOUT = 5
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

CORE_DEPENDENCIES = (
    ("cryptography", "cryptography"),
    ("py7zr", "py7zr"),
    ("pyzipper", "pyzipper"),
    ("lz4", "lz4"),
    ("zstandard", "zstandard"),
    ("brotli", "brotli"),
)
_BROWSER_LABELS = (("chrome", "Chrome"), ("msedge", "Edge"))
_CHROMIUM_EXECUTABLES = (
    "chrome-win/chrome.exe",
    "chrome-win64/chrome.exe",
    "chrome-linux/chrome",
    "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
)


def _result(check_id: str, required: bool, status: str, message: str) -> dict:
    return {"id": check_id, "required": required, "status": status, "message": message}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    try:
        return str(value)
    except Exception:
        return ""


def _run(command, timeout: int = PROBE_TIMEOUT) -> dict:
    """Run one harmless probe; never echo the command or its raw output."""
    try:
        completed = subprocess.run(
            [str(part) for part in command],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {"state": "timeout"}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"state": "unavailable"}
    return {
        "state": "ok" if completed.returncode == 0 else "failed",
        "code": completed.returncode,
        "stdout": _text(completed.stdout),
        "stderr": _text(completed.stderr),
    }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return ""


def _missing_dependencies() -> list[str]:
    return [label for module, label in CORE_DEPENDENCIES if not _module_available(module)]


def _sevenzip_executable():
    # Imported lazily: a broken core dependency must not break the whole report.
    from .formats import sevenzip_executable

    return sevenzip_executable()


def _which(name: str):
    return shutil.which(name)


def _system_browsers() -> dict:
    """Reuse the desktop probe when possible; never launch or import a browser."""
    try:
        from .desktop.api import installed_browsers

        found = installed_browsers()
        return {key: bool(found.get(key)) for key, _ in _BROWSER_LABELS}
    except Exception:
        return _system_browsers_fallback()


def _system_browsers_fallback() -> dict:
    found = {"chrome": False, "msedge": False}
    if os.name == "nt":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for key, rel in (("chrome", r"Google\Chrome\Application\chrome.exe"),
                         ("msedge", r"Microsoft\Edge\Application\msedge.exe")):
            found[key] = any(root and (Path(root) / rel).is_file() for root in roots)
    else:
        found["chrome"] = bool(shutil.which("google-chrome") or shutil.which("google-chrome-stable"))
        found["msedge"] = bool(shutil.which("microsoft-edge"))
    return found


def _playwright_browsers_root() -> Path | None:
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        if override == "0":
            try:
                spec = importlib.util.find_spec("playwright")
                origin = Path(spec.origin) if spec and spec.origin else None
            except Exception:
                origin = None
            return origin.parent / "driver" / "package" / ".local-browsers" if origin else None
        return Path(override)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return Path(local) / "ms-playwright" if local else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    cache = os.environ.get("XDG_CACHE_HOME")
    return (Path(cache) if cache else Path.home() / ".cache") / "ms-playwright"


def _chromium_available() -> bool | None:
    try:
        root = _playwright_browsers_root()
        if root is None:
            return None
        if not root.is_dir():
            return False
        for entry in root.iterdir():
            if entry.is_dir() and entry.name.startswith("chromium-"):
                if ((entry / "INSTALLATION_COMPLETE").is_file()
                        or any((entry / rel).is_file() for rel in _CHROMIUM_EXECUTABLES)):
                    return True
    except OSError:
        return None
    return False


def _check_python() -> dict:
    current = (sys.version_info.major, sys.version_info.minor)
    shown = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    minimum = ".".join(str(part) for part in MIN_PYTHON)
    if current < MIN_PYTHON:
        return _result("python", True, "error", f"Python {shown} 低于最低要求 {minimum}，请升级后再使用")
    return _result("python", True, "ok", f"Python {shown}，符合最低要求 {minimum}")


def _check_dependencies() -> dict:
    missing = _missing_dependencies()
    if missing:
        return _result("dependencies", True, "error",
                       "缺少核心依赖：" + "、".join(missing) + "；请重新安装 misong 及其依赖")
    names = "、".join(label for _, label in CORE_DEPENDENCIES)
    return _result("dependencies", True, "ok", f"核心依赖齐全（{names}）")


def _check_7zip() -> dict:
    try:
        executable = _sevenzip_executable()
    except Exception:
        return _result("7zip", True, "error", "无法读取 7-Zip 探测入口，请重新安装核心依赖")
    if not executable:
        return _result("7zip", True, "error", "未找到 7-Zip 可执行文件；请确认内置 7za.exe 完整，或安装 7-Zip")
    probe = _run([executable, "i"])
    if probe["state"] == "timeout":
        return _result("7zip", True, "error", "7-Zip 探测超时；程序可能无法启动或被安全软件拦截")
    if probe["state"] == "unavailable":
        return _result("7zip", True, "error", "7-Zip 已找到，但无法执行")
    if probe["state"] == "failed":
        return _result("7zip", True, "error", f"7-Zip 返回异常状态（代码 {probe.get('code')}）")
    version = re.search(r"7-Zip[^\d]{0,20}(\d+(?:\.\d+)+)", probe.get("stdout", ""))
    suffix = f" {version.group(1)}" if version else ""
    return _result("7zip", True, "ok", f"7-Zip{suffix} 可执行")


def _check_node() -> dict:
    executable = _which("node")
    if not executable:
        return _result("node", False, "warn", "未找到 Node.js；魔曰编解码不可用（基础打包不受影响）")
    probe = _run([executable, "--version"])
    if probe["state"] == "timeout":
        return _result("node", False, "warn", "Node.js 探测超时；魔曰可能不可用")
    if probe["state"] == "unavailable":
        return _result("node", False, "warn", "Node.js 已找到，但无法执行；魔曰可能不可用")
    if probe["state"] == "failed":
        return _result("node", False, "warn", f"Node.js 返回异常状态（代码 {probe.get('code')}）；魔曰可能不可用")
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", probe.get("stdout", ""))
    if not match:
        return _result("node", False, "warn", "Node.js 已找到，但无法识别版本；魔曰可能不可用")
    shown = ".".join(match.groups())
    if int(match.group(1)) < MIN_NODE:
        return _result("node", False, "warn", f"Node.js v{shown} 低于建议的 {MIN_NODE}；魔曰可能不可用")
    return _result("node", False, "ok", f"Node.js v{shown} 可用（魔曰）")


def _check_playwright() -> dict:
    if not _module_available("playwright"):
        return _result("playwright", False, "warn", "未安装 Playwright；网页上传不可用（基础打包不受影响）")
    version = _package_version("playwright")
    suffix = f" {version}" if re.fullmatch(r"\d[\w.+-]*", version or "") else ""
    return _result("playwright", False, "ok", f"Playwright{suffix} 已安装（网页上传）")


def _check_browsers() -> dict:
    playwright = _module_available("playwright")
    chromium = _chromium_available() if playwright else False
    if chromium:
        return _result("browsers", False, "ok", "Playwright Chromium 已安装")
    channels = [label for key, label in _BROWSER_LABELS if _system_browsers().get(key)]
    found = "/".join(channels)
    if chromium is None and playwright and not channels:
        return _result("browsers", False, "warn", "无法确认 Playwright Chromium 是否安装；请运行 playwright install chromium")
    if channels and playwright:
        return _result("browsers", False, "ok",
                       f"Playwright Chromium 未安装，但已找到系统 {found}；网页上传仍可使用")
    if channels:
        return _result("browsers", False, "warn", f"已找到系统 {found}，但未安装 Playwright；网页上传不可用")
    if not playwright:
        return _result("browsers", False, "warn", "未找到可用浏览器；网页上传不可用")
    return _result("browsers", False, "warn", "未找到 Playwright Chromium 或系统 Chrome/Edge；请运行 playwright install chromium")


def _check_desktop() -> dict:
    if not _module_available("webview"):
        return _result("desktop", False, "warn", "未安装 pywebview；桌面界面不可用（CLI 与基础打包不受影响）")
    return _result("desktop", False, "ok", "桌面端依赖 pywebview 已安装")


_CHECKS = (
    ("python", True, _check_python),
    ("dependencies", True, _check_dependencies),
    ("7zip", True, _check_7zip),
    ("node", False, _check_node),
    ("playwright", False, _check_playwright),
    ("browsers", False, _check_browsers),
    ("desktop", False, _check_desktop),
)


def _guarded(check_id: str, required: bool, probe) -> dict:
    try:
        return probe()
    except Exception:
        # Never echo exception text: paths and environment values may appear there.
        status = "error" if required else "warn"
        return _result(check_id, required, status, "检查未能完成，请稍后重试")


def check_environment() -> dict:
    """Return ``{"ok": bool, "checks": [...]}`` without networking or writes.

    ``ok`` is false only when a required check (Python, core dependencies or
    7-Zip) errors. Missing optional tooling is surfaced as a warning.
    """
    checks = [_guarded(check_id, required, probe) for check_id, required, probe in _CHECKS]
    return {"ok": all(check["status"] != "error" for check in checks), "checks": checks}
