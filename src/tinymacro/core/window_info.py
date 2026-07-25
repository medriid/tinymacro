"""Best-effort active-window title lookup for the wait-for-window step.

Windows is supported via the Win32 API; X11 via ``xdotool``/``xprop`` if present.
When the title can't be determined, callers treat the condition as unmet and fall
back to the step's on-missing policy.
"""
from __future__ import annotations

import shutil
import subprocess
import sys


def active_window_title() -> str | None:
    if sys.platform == "win32":
        return _windows_title()
    return _x11_title()


def _windows_title() -> str | None:
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value or None
    except Exception:  # noqa: BLE001
        return None


def _x11_title() -> str | None:
    if shutil.which("xdotool"):
        try:
            out = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            title = out.stdout.strip()
            return title or None
        except Exception:  # noqa: BLE001
            return None
    return None
