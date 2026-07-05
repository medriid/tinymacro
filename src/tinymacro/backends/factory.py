from __future__ import annotations

import os

from tinymacro.backends.base import InputBackend
from tinymacro.backends.fake import FakeBackend


def detect_session() -> str:
    return os.environ.get("XDG_SESSION_TYPE", "").lower()


def create_backend(name: str = "auto") -> InputBackend:
    if name == "fake":
        return FakeBackend()
    if name == "auto":
        session = detect_session()
        name = "wayland" if session == "wayland" else "x11"
    if name in {"x11", "xorg"}:
        from tinymacro.backends.x11 import X11Backend

        return X11Backend()
    if name in {"wayland", "evdev", "wayland-evdev"}:
        from tinymacro.backends.evdev_wayland import WaylandEvdevBackend

        return WaylandEvdevBackend()
    raise ValueError(f"Unknown backend: {name}")
