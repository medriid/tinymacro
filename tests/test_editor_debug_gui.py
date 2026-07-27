from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QColor

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.gui.editor import EditorDialog


def _macro() -> Macro:
    return Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "press", key="b"),
        MacroEvent(2_000_000, "key", "press", key="c"),
    ])


def test_live_playhead_highlights_and_clears(qtbot):
    editor = EditorDialog(_macro(), live=True)
    qtbot.addWidget(editor)

    editor.set_playing_index(1)
    item = editor._item_for_index(1)
    assert item is not None
    assert editor._playing_item is item
    assert item.background(0).color() == QColor(EditorDialog._PLAYING_TINT)

    editor.clear_playing()
    assert editor._playing_item is None


def test_breakpoint_toggle_emits_and_paints(qtbot):
    editor = EditorDialog(_macro(), live=True)
    qtbot.addWidget(editor)

    emitted: list[set] = []
    editor.breakpoints_changed.connect(emitted.append)

    editor.tree.setCurrentItem(editor._item_for_index(1))
    editor.toggle_breakpoint()
    assert editor.breakpoints == {1}
    assert emitted and emitted[-1] == {1}
    # The '#' cell is prefixed with a dot for a breakpointed row.
    assert editor._item_for_index(1).text(0).startswith("●")

    editor.tree.setCurrentItem(editor._item_for_index(1))
    editor.toggle_breakpoint()
    assert editor.breakpoints == set()


def test_structural_edit_clears_breakpoints(qtbot):
    editor = EditorDialog(_macro(), live=True)
    qtbot.addWidget(editor)
    editor.tree.setCurrentItem(editor._item_for_index(2))
    editor.toggle_breakpoint()
    assert editor.breakpoints == {2}

    # Deleting an event changes the event count, so positional breakpoints drop.
    editor.tree.setCurrentItem(editor._item_for_index(0))
    editor.delete_selected()
    assert editor.breakpoints == set()


def test_live_edit_emits_macro_changed(qtbot):
    editor = EditorDialog(_macro(), live=True)
    qtbot.addWidget(editor)
    seen: list[Macro] = []
    editor.macro_changed.connect(seen.append)
    editor.tree.setCurrentItem(editor._item_for_index(0))
    editor.delete_selected()
    assert seen and len(seen[-1].events) == 2
