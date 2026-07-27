"""End-to-end: a breakpoint set in the editor pauses a real threaded playback."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow


def test_breakpoint_pauses_and_resumes_real_playback(qtbot):
    backend = FakeBackend()
    window = MainWindow(Settings(backend="fake", loop_count=1), backend, persist_settings=False)
    qtbot.addWidget(window)
    window.macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "press", key="b"),
        MacroEvent(2_000_000, "key", "press", key="c"),
    ])

    # Keep playback fast and the pause-poll tight so the test is deterministic
    # under full-suite load (no reliance on wall-clock pacing).
    window.player.sleeper = lambda s: time.sleep(min(s, 0.001))

    window.open_editor()
    qtbot.addWidget(window._editor)
    window._editor.tree.setCurrentItem(window._editor._item_for_index(1))
    window._editor.toggle_breakpoint()
    assert window.player.breakpoints == {1}

    window.toggle_playback()  # starts playback on a background thread
    # It should stop at the breakpoint before emitting 'b'.
    qtbot.waitUntil(lambda: window.player.state.paused, timeout=3000)
    pressed = [e.key for e in backend.emitted if e.action == "press"]
    assert pressed == ["a"]
    assert window.player.state.current_index == 1
    assert window._editor._paused_index == 1

    window.player.resume()
    qtbot.waitUntil(lambda: not window.player.state.playing, timeout=3000)
    pressed = [e.key for e in backend.emitted if e.action == "press"]
    assert pressed == ["a", "b", "c"]
