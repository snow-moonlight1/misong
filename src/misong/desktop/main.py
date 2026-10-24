"""Desktop shell: the system Edge WebView2 (through pywebview) hosting the local web UI."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .api import Api

WEB = Path(__file__).with_name("web")


class MissingWebView(RuntimeError):
    """pywebview (the optional ``gui`` extra) is not installed."""


def _dpi_aware():
    if os.name != "nt":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor: crisp text on scaled displays
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _bind_drop(window):
    """Forward dropped files' real paths (pywebview DOM extension) to the page."""
    try:
        from webview.dom import DOMEventHandler
    except ImportError:
        return

    def on_drop(event):
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            window.evaluate_js(f"window.misongDrop && window.misongDrop({json.dumps(paths, ensure_ascii=False)})")
    try:
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    except Exception:  # noqa: BLE001 - drag and drop is optional; pickers still work
        pass


def main(debug: bool | None = None) -> int:
    try:
        import webview
    except ImportError as exc:
        raise MissingWebView('缺少 pywebview：运行 .venv\\Scripts\\python -m pip install -e ".[gui]"') from exc
    _dpi_aware()
    api = Api()
    window = webview.create_window("密送（Misong）资源发布台", url=str(WEB / "index.html"), js_api=api,
                                   width=1320, height=880, min_size=(1100, 720),
                                   background_color="#F7F6F3", text_select=True)
    api._attach(window)
    window.events.closing += api._on_closing
    debug = bool(os.environ.get("MISONG_DEBUG", os.environ.get("NDE_DEBUG"))) if debug is None else debug
    webview.start(_bind_drop, window, debug=debug, private_mode=True)
    return 0


def launch(legacy: bool = False, debug: bool | None = None) -> int:
    """Open the WebView2 desktop UI; fall back to the legacy Tk window when pywebview is missing."""
    if not legacy:
        try:
            return main(debug=debug)
        except MissingWebView as exc:
            print(f"[warn] {exc}；改用旧版 Tk 界面", file=sys.stderr)
    from ..gui import main as legacy_main
    return legacy_main() or 0


if __name__ == "__main__":
    raise SystemExit(launch())
