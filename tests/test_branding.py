"""The installed UI uses the same transparent artwork at native Windows sizes."""
import ctypes
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from misong.desktop import branding


@pytest.mark.parametrize("size", [16, 20, 24, 32, 40, 48, 64, 96, 128, 256])
def test_windows_icon_contains_transparent_native_size(size, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with Image.open(branding.ICON_ICO) as icon:
        frame = icon.ico.getimage((size, size))
        assert frame.size == (size, size)
        alpha = frame.getchannel("A")
        assert alpha.getextrema() == (0, 255)
        left, _, right, _ = alpha.point(lambda value: 255 if value > 32 else 0).getbbox()
        assert right - left >= size * 0.8


def test_png_remains_available_outside_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with Image.open(branding.LOGO_PNG) as logo:
        assert logo.mode == "RGBA"
        assert logo.size == (512, 512)
        assert logo.getpixel((0, 0))[3] == 0
        assert logo.getpixel((256, 256))[3] >= 250


def test_windows_app_identity_is_stable_and_not_python(monkeypatch):
    calls = []
    monkeypatch.setattr(branding, "os", SimpleNamespace(name="nt"))
    shell = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=calls.append)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(shell32=shell), raising=False)
    branding.configure_windows_app()
    assert calls == ["Misong.Desktop"]


@pytest.mark.parametrize("error", [OSError, AttributeError])
def test_missing_shell_identity_api_does_not_block_ui(monkeypatch, error):
    def unavailable(_):
        raise error("Unavailable in this environment")

    monkeypatch.setattr(branding, "os", SimpleNamespace(name="nt"))
    shell = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=unavailable)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(shell32=shell), raising=False)
    branding.configure_windows_app()


def test_non_windows_does_not_call_shell_api(monkeypatch):
    monkeypatch.setattr(branding, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(ctypes, "windll", None, raising=False)
    branding.configure_windows_app()


@pytest.mark.parametrize("platform, icon", [("nt", branding.ICON_ICO), ("posix", branding.LOGO_PNG)])
def test_desktop_sets_identity_before_window_and_uses_platform_icon(monkeypatch, platform, icon):
    from misong.desktop import main as desktop

    calls = []

    class Hook(list):
        def __iadd__(self, handler):
            self.append(handler)
            return self

    window = SimpleNamespace(events=SimpleNamespace(closing=Hook()))
    api = SimpleNamespace(_attach=lambda _: None, _on_closing=lambda: None)

    def create_window(*args, **kwargs):
        calls.append("window")
        return window

    def start(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(desktop, "os", SimpleNamespace(name=platform, environ={}))
    monkeypatch.setattr(desktop, "configure_windows_app", lambda: calls.append("identity"))
    monkeypatch.setattr(desktop, "_dpi_aware", lambda: None)
    monkeypatch.setattr(desktop, "Api", lambda: api)
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(create_window=create_window, start=start))
    assert desktop.main(debug=False) == 0
    assert calls[:2] == ["identity", "window"]
    assert calls[2]["icon"] == str(icon)


@pytest.mark.skipif(sys.platform != "win32", reason="Native Tk window icons require Windows")
def test_legacy_tk_main_window_has_both_native_icons(monkeypatch):
    import tkinter as tk
    from misong import gui

    # Build just the original shell, without account widgets or local user state.
    monkeypatch.setattr(gui.App, "_style", lambda self: None)
    monkeypatch.setattr(gui.App, "_build", lambda self: None)
    root = tk.Tk()
    root.withdraw()
    try:
        gui.App(root)
        root.update_idletasks()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetParent.argtypes = [ctypes.c_void_p]
        user32.GetParent.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        hwnd = user32.GetParent(root.winfo_id())
        assert hwnd
        assert user32.SendMessageW(hwnd, 0x7F, 0, 0)  # WM_GETICON / ICON_SMALL
        assert user32.SendMessageW(hwnd, 0x7F, 1, 0)  # WM_GETICON / ICON_BIG
    finally:
        root.destroy()
