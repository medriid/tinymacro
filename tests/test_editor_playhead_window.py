from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow


def _macro() -> Macro:
    return Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "press", key="b"),
    ])


def test_editor_opens_non_modal_single_instance(qtbot):
    window = MainWindow(Settings(backend="fake"), FakeBackend(), persist_settings=False)
    qtbot.addWidget(window)
    window.macro = _macro()

    window.open_editor()
    editor = window._editor
    assert editor is not None
    assert editor.live is True
    assert not editor.isModal()  # non-modal so it can stay open during playback
    qtbot.addWidget(editor)

    window.open_editor()  # a second call reuses the same editor
    assert window._editor is editor


def test_step_and_breakpoint_route_to_editor(qtbot):
    window = MainWindow(Settings(backend="fake"), FakeBackend(), persist_settings=False)
    qtbot.addWidget(window)
    window.macro = _macro()
    window.open_editor()
    qtbot.addWidget(window._editor)

    # Breakpoints set in the editor flow straight through to the player (the
    # breakpoints_changed signal is connected in open_editor).
    window._editor.tree.setCurrentItem(window._editor._item_for_index(1))
    window._editor.toggle_breakpoint()
    assert window.player.breakpoints == {1}

    # Simulate an in-progress run so _update_state doesn't clear the playhead.
    window.player.state.playing = True
    # With the playhead armed, a step signal highlights the editor row.
    window._prepare_playhead(True)
    window._on_step_reached(1)
    assert window._editor._playing_item is window._editor._item_for_index(1)

    # A breakpoint hit marks the paused row and does not raise.
    window._on_breakpoint_hit(1)
    assert window._editor._paused_index == 1
    window.player.state.playing = False


def test_editor_closed_clears_reference(qtbot):
    window = MainWindow(Settings(backend="fake"), FakeBackend(), persist_settings=False)
    qtbot.addWidget(window)
    window.macro = _macro()
    window.open_editor()
    editor = window._editor
    qtbot.addWidget(editor)
    editor.reject()  # close it
    assert window._editor is None
    assert window.player.breakpoints == set()
