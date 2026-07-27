from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.core.events import MacroEvent
from tinymacro.core.library import MacroLibrary
from tinymacro.core.macro import Macro
from tinymacro.gui.playlist_dialog import PlaylistDialog


def _write_macro(path, key: str) -> None:
    Macro(events=[MacroEvent(0, "key", "press", key=key)]).save(path)


def test_playlist_dialog_add_reorder_and_play(qtbot, tmp_path):
    one = tmp_path / "one.tmacc"
    two = tmp_path / "two.tmacc"
    _write_macro(one, "a")
    _write_macro(two, "b")

    dialog = PlaylistDialog(MacroLibrary(), docked=False)
    qtbot.addWidget(dialog)

    dialog._add_path(str(one))
    dialog._add_path(str(two))
    assert [i.display_name for i in dialog.playlist.items] == ["one", "two"]

    # Reorder via the dialog helper, then set a repeat on the selected row.
    dialog.list.setCurrentRow(1)
    dialog._move(-1)
    assert [i.display_name for i in dialog.playlist.items] == ["two", "one"]
    dialog.list.setCurrentRow(0)
    dialog.repeat_spin.setValue(3)
    assert dialog.playlist.items[0].repeat == 3

    built = []
    dialog.play_requested.connect(built.append)
    dialog._play()
    assert len(built) == 1
    # two×3 + one×1 = 4 key presses stitched together.
    assert len([e for e in built[0].events if e.kind == "key"]) == 4


def test_playlist_dialog_rejects_wrong_variant(qtbot, tmp_path, monkeypatch):
    # A Studio (.tmacd) macro must not be addable to a classic playlist.
    docked = tmp_path / "docked.tmacd"
    Macro(events=[MacroEvent(0, "key", "press", key="a")], docked=True).save(docked)

    dialog = PlaylistDialog(MacroLibrary(), docked=False)
    qtbot.addWidget(dialog)

    warned = []
    monkeypatch.setattr(
        "tinymacro.gui.playlist_dialog.QMessageBox.warning",
        lambda *a, **k: warned.append(a),
    )
    dialog._add_path(str(docked))
    assert not dialog.playlist.items
    assert warned
