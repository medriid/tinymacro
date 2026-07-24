from __future__ import annotations

from types import SimpleNamespace

import pytest

from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import Hotkey, HotkeySet


def test_hotkey_parse_matches_and_stringifies():
    hotkey = Hotkey.parse("Ctrl + Shift + Alt + R")

    assert hotkey.matches(["alt", "shift", "control", "r"])
    assert "R" in str(hotkey)


def test_hotkey_conflicts_are_rejected():
    hotkeys = HotkeySet(record=Hotkey.parse("f8"), play=Hotkey.parse("f8"))

    with pytest.raises(ValueError):
        hotkeys.validate()


def test_wayland_hotkeys_start_input_reader_without_recording(monkeypatch):
    from tinymacro.backends import evdev_wayland

    class FakeInputDevice:
        def __init__(self, path: str) -> None:
            self.path = path
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeThread:
        def __init__(self, target, daemon: bool) -> None:
            self.target = target
            self.daemon = daemon
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.started

        def join(self, timeout: float | None = None) -> None:
            self.started = False

    fake_ecodes = SimpleNamespace()
    fake_evdev = SimpleNamespace(InputDevice=FakeInputDevice, UInput=object, AbsInfo=object, ecodes=fake_ecodes)
    threads: list[FakeThread] = []

    def make_thread(target, daemon: bool) -> FakeThread:
        thread = FakeThread(target, daemon)
        threads.append(thread)
        return thread

    monkeypatch.setitem(__import__("sys").modules, "evdev", fake_evdev)
    monkeypatch.setattr(evdev_wayland.os, "access", lambda path, mode: True)
    monkeypatch.setattr(evdev_wayland.threading, "Thread", make_thread)

    calls = []
    backend = evdev_wayland.WaylandEvdevBackend(devices=["/dev/input/event0"])
    backend.start_hotkeys(lambda pressed: calls.append(pressed))

    assert backend.devices
    assert backend.devices[0].path == "/dev/input/event0"
    assert backend._capture_callback is None
    assert threads and threads[0].started
    backend._update_hotkeys(MacroEvent(0, "key", "press", key="f8"))
    backend._update_hotkeys(MacroEvent(0, "key", "press", key="f8"))
    assert calls == [frozenset({"f8"})]

    device = backend.devices[0]
    backend.stop_hotkeys()

    assert device.closed


def test_wayland_evdev_tuple_button_name_records_mouse(monkeypatch):
    from tinymacro.backends import evdev_wayland

    class FakeInputDevice:
        pass

    fake_ecodes = SimpleNamespace(
        EV_KEY=1,
        KEY={272: ("BTN_LEFT", "BTN_MOUSE")},
        BTN={},
    )
    fake_evdev = SimpleNamespace(InputDevice=FakeInputDevice, UInput=object, AbsInfo=object, ecodes=fake_ecodes)
    monkeypatch.setitem(__import__("sys").modules, "evdev", fake_evdev)

    backend = evdev_wayland.WaylandEvdevBackend(devices=[])
    event = SimpleNamespace(type=fake_ecodes.EV_KEY, code=272, value=1)

    macro_event = backend._convert_event(event)

    assert macro_event.kind == "mouse"
    assert macro_event.action == "press"
    assert macro_event.button == "left"
