from __future__ import annotations

import os
import sys

from tinymacro.backends.base import InputBackend
from tinymacro.backends.fake import FakeBackend


def detect_session() -> str:
    # WAYLAND_DISPLAY is the most reliable signal — some launchers leave
    # XDG_SESSION_TYPE unset even under Wayland, which would misroute us to x11.
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    return os.environ.get("XDG_SESSION_TYPE", "").lower()


def create_backend(name: str = "auto") -> InputBackend:
    if name == "fake":
        return FakeBackend()
    if name == "auto":
        if sys.platform == "win32":
            name = "windows"
        elif sys.platform == "darwin":
            name = "macos"
        else:
            session = detect_session()
            name = "wayland" if session == "wayland" else "x11"
    if name in {"windows", "win32"}:
        from tinymacro.backends.windows import WindowsBackend

        return WindowsBackend()
    if name in {"macos", "mac", "darwin", "cocoa"}:
        from tinymacro.backends.macos import MacBackend

        return MacBackend()
    if name in {"x11", "xorg"}:
        from tinymacro.backends.x11 import X11Backend

        return X11Backend()
    if name in {"wayland", "evdev", "wayland-evdev"}:
        from tinymacro.backends.evdev_wayland import WaylandEvdevBackend

        return WaylandEvdevBackend()
    raise ValueError(f"Unknown backend: {name}")
