"""Headless coverage for the pynput-based backends (X11 + macOS).

A fake ``pynput`` module lets us construct the real backend classes and verify
capture/emit/type/hotkey routing without an X or Quartz session.
"""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from tinymacro.backends import factory
from tinymacro.backends._pynput import _button_name, _key_name
from tinymacro.core.events import MacroEvent


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []


class _FakeListener:
    def __init__(self, **handlers) -> None:
        self.handlers = handlers
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FakeMouseController:
    def __init__(self) -> None:
        self.position = (0, 0)
        self.rec = _Recorder()

    def press(self, button) -> None:
        self.rec.calls.append(("press", button))

    def release(self, button) -> None:
        self.rec.calls.append(("release", button))

    def scroll(self, dx, dy) -> None:
        self.rec.calls.append(("scroll", dx, dy))


class _FakeKeyboardController:
    def __init__(self) -> None:
        self.rec = _Recorder()

    def press(self, key) -> None:
        self.rec.calls.append(("press", key))

    def release(self, key) -> None:
        self.rec.calls.append(("release", key))

    def type(self, text) -> None:
        self.rec.calls.append(("type", text))


def _install_fake_pynput(monkeypatch):
    keyboard = ModuleType("pynput.keyboard")
    keyboard.Key = SimpleNamespace(enter="<enter>", cmd="<cmd>", scroll_lock="<scroll>")
    keyboard.Listener = _FakeListener
    keyboard.Controller = _FakeKeyboardController

    mouse = ModuleType("pynput.mouse")
    mouse.Button = SimpleNamespace(left="<left>", right="<right>", middle="<middle>")
    mouse.Listener = _FakeListener
    mouse.Controller = _FakeMouseController

    pynput = ModuleType("pynput")
    pynput.keyboard = keyboard
    pynput.mouse = mouse

    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)
    monkeypatch.setitem(sys.modules, "pynput.mouse", mouse)


# -- name normalisation -------------------------------------------------------

def test_command_key_normalises_to_super():
    assert _key_name(SimpleNamespace(char=None, name="cmd")) == "super"
    assert _key_name(SimpleNamespace(char=None, name="cmd_r")) == "super"


def test_char_key_lowercased_and_button_stripped():
    assert _key_name(SimpleNamespace(char="A")) == "a"
    assert _button_name(SimpleNamespace(name="left")) == "left"


# -- factory routing ----------------------------------------------------------

def test_auto_selects_macos_backend_on_darwin(monkeypatch):
    fake_module = ModuleType("tinymacro.backends.macos")

    class DummyMac:
        name = "darwin"

    fake_module.MacBackend = DummyMac
    monkeypatch.setitem(sys.modules, "tinymacro.backends.macos", fake_module)
    monkeypatch.setattr(factory.sys, "platform", "darwin")

    backend = factory.create_backend("auto")

    assert backend.name == "darwin"


@pytest.mark.parametrize("alias", ["macos", "mac", "darwin", "cocoa"])
def test_macos_aliases_all_resolve(monkeypatch, alias):
    _install_fake_pynput(monkeypatch)
    backend = factory.create_backend(alias)
    assert backend.name == "darwin"
    assert backend.capabilities.requires_privileges is True


# -- real backend classes over the fake pynput --------------------------------

def _mac_backend(monkeypatch):
    _install_fake_pynput(monkeypatch)
    from tinymacro.backends.macos import MacBackend

    return MacBackend()


def test_capture_routes_events(monkeypatch):
    backend = _mac_backend(monkeypatch)
    seen: list[MacroEvent] = []
    backend.start_capture(seen.append)

    ml = backend._mouse_listener
    kl = backend._keyboard_listener
    assert ml.started and kl.started

    ml.handlers["on_click"](5, 6, SimpleNamespace(name="left"), True)
    kl.handlers["on_press"](SimpleNamespace(char="a"))

    kinds = [(e.kind, e.action) for e in seen]
    assert ("mouse", "press") in kinds
    assert ("key", "press") in kinds

    backend.stop_capture()
    assert ml.stopped and backend._mouse_listener is None


def test_emit_and_type_text(monkeypatch):
    backend = _mac_backend(monkeypatch)
    backend.emit(MacroEvent(0, "mouse", "press", button="left", x=3, y=4))
    assert backend._mouse_controller.position == (3, 4)
    assert ("press", "<left>") in backend._mouse_controller.rec.calls

    backend.type_text("hi")
    assert ("type", "hi") in backend._keyboard_controller.rec.calls


def test_hotkeys_accumulate_and_clear(monkeypatch):
    backend = _mac_backend(monkeypatch)
    combos: list[frozenset[str]] = []
    backend.start_hotkeys(combos.append)
    listener = backend._hotkey_listener

    listener.handlers["on_press"](SimpleNamespace(char=None, name="ctrl_l"))
    listener.handlers["on_press"](SimpleNamespace(char="s"))
    assert combos[-1] == frozenset({"ctrl", "s"})

    listener.handlers["on_release"](SimpleNamespace(char="s"))
    backend.start_hotkeys(combos.append)  # idempotent
    backend.stop_hotkeys()
    assert backend._hotkey_listener is None
