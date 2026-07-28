from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import Hotkey, HotkeySet
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow


def test_main_window_initial_state(qtbot):
    window = MainWindow(Settings(backend="fake"), FakeBackend(), persist_settings=False)
    qtbot.addWidget(window)

    assert "Tiny Macro" in window.windowTitle()
    assert not window.play_action.isEnabled()


def test_main_window_record_hotkey_toggles_recording(qtbot):
    backend = FakeBackend()
    settings = Settings(backend="fake", hotkeys=HotkeySet(record=Hotkey.parse("f8")))
    window = MainWindow(settings, backend, persist_settings=False)
    qtbot.addWidget(window)

    backend.press_hotkey("f8")

    assert window.recorder.recording


def test_preferences_loop_default_updates_playback_controls(qtbot, monkeypatch):
    class _Stub:
        def connect(self, *_a, **_k) -> None:
            pass

    class FakePreferencesDialog:
        replay_tour = _Stub()  # mirrors the real dialog's signal interface
        open_theme_editor = _Stub()

        def __init__(self, settings, parent=None) -> None:
            self.settings = settings

        def exec(self) -> bool:
            self.settings.loop_count = 100
            self.settings.speed = 2.0
            return True

    captured = {}
    settings = Settings(backend="fake", loop_count=1, speed=1.0)
    window = MainWindow(settings, FakeBackend(), persist_settings=False)
    window.macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    qtbot.addWidget(window)
    monkeypatch.setattr("tinymacro.gui.main_window.PreferencesDialog", FakePreferencesDialog)
    monkeypatch.setattr(Settings, "save", lambda self: None)
    monkeypatch.setattr(
        type(window.player),
        "start",
        lambda self, macro, loop_count, speed: captured.update(loop_count=loop_count, speed=speed),
    )

    window.open_preferences()
    window.toggle_playback()

    assert window.loop_spin.value() == 100
    assert window.speed_spin.value() == 2.0
    assert captured == {"loop_count": 100, "speed": 2.0}
