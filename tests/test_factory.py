from __future__ import annotations

import sys
from types import ModuleType

from tinymacro.backends import factory
from tinymacro.backends.base import InputBackend
from tinymacro.core.events import MacroEvent


class DummyWindowsBackend(InputBackend):
    name = "windows"

    def start_capture(self, callback) -> None:
        pass

    def stop_capture(self) -> None:
        pass

    def emit(self, event: MacroEvent) -> None:
        pass


def test_auto_selects_windows_backend_on_windows(monkeypatch):
    fake_module = ModuleType("tinymacro.backends.windows")
    fake_module.WindowsBackend = DummyWindowsBackend
    monkeypatch.setitem(sys.modules, "tinymacro.backends.windows", fake_module)
    monkeypatch.setattr(factory.sys, "platform", "win32")

    backend = factory.create_backend("auto")

    assert backend.name == "windows"


def test_detect_session_prefers_wayland_display(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert factory.detect_session() == "wayland"


def test_detect_session_falls_back_to_xdg(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert factory.detect_session() == "x11"


def test_windows_key_names_and_vk_codes():
    from tinymacro.backends.windows import _key_name, _vk_code

    assert _key_name(0x77) == "f8"
    assert _vk_code("f8") == 0x77
    assert _vk_code("Ctrl") == 0x11
