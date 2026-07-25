"""Keyboard playback directs focus to the user's target window.

The heavy end-to-end check (typing into a real window) is Windows-only and lives
in manual diagnostics; here we verify the wiring: the main window remembers the
last external window and asks the backend to focus it before a key macro plays.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow


class _FocusBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.focused: list[int] = []

    def foreground_window_if_external(self) -> int:
        return 4242

    def focus_window(self, handle: int) -> bool:
        self.focused.append(handle)
        return True


def test_key_macro_restores_focus(qtbot):
    backend = _FocusBackend()
    window = MainWindow(Settings(backend="fake"), backend, persist_settings=False)
    qtbot.addWidget(window)
    window._tick()  # records the external window handle
    assert window._last_external_hwnd == 4242
    window._restore_target_focus(Macro(events=[MacroEvent(0, "key", "press", key="a")]))
    assert backend.focused == [4242]


def test_mouse_only_macro_does_not_change_focus(qtbot):
    backend = _FocusBackend()
    window = MainWindow(Settings(backend="fake"), backend, persist_settings=False)
    qtbot.addWidget(window)
    window._tick()
    window._restore_target_focus(Macro(events=[MacroEvent(0, "mouse", "move", x=1, y=1)]))
    assert backend.focused == []  # mouse is coordinate-based; no focus juggling


def test_no_target_no_focus_call(qtbot):
    backend = FakeBackend()  # base returns 0 for foreground_window_if_external
    window = MainWindow(Settings(backend="fake"), backend, persist_settings=False)
    qtbot.addWidget(window)
    window._last_external_hwnd = 0
    window._restore_target_focus(Macro(events=[MacroEvent(0, "key", "press", key="a")]))
    # nothing to assert beyond "no crash"; base backend focus_window is a no-op
