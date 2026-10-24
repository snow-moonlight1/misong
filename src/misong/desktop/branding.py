"""Shared, installed-package paths and Windows identity for the desktop shells."""
from __future__ import annotations

import os
from pathlib import Path

BRANDING = Path(__file__).resolve().with_name("web") / "branding"
LOGO_PNG = BRANDING / "logo.png"
ICON_ICO = BRANDING / "logo.ico"
APP_USER_MODEL_ID = "Misong.Desktop"


def configure_windows_app() -> None:
    """Keep Misong windows in their own taskbar group instead of Python's group."""
    if os.name != "nt":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        # An unavailable shell identity API must not prevent opening the UI.
        pass
