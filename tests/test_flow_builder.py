from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.core.events import MacroEvent
from tinymacro.core.library import MacroLibrary
from tinymacro.core.macro import Macro
from tinymacro.gui.flow_builder import FlowBuilderDialog


def _write(path, key: str) -> None:
    Macro(events=[MacroEvent(0, "key", "press", key=key)]).save(path)


def test_flow_builder_add_reorder_and_play(qtbot, tmp_path):
    one = tmp_path / "one.tmacc"
    two = tmp_path / "two.tmacc"
    _write(one, "a")
    _write(two, "b")

    dialog = FlowBuilderDialog(MacroLibrary(), docked=False)
    qtbot.addWidget(dialog)

    dialog._add_path(str(one))
    dialog._add_path(str(two))
    assert [i.display_name for i in dialog.playlist.items] == ["one", "two"]
    # One Start node + two macro nodes.
    assert len(dialog._nodes) == 3

    # Select and reorder.
    dialog._nodes[2].setSelected(True)  # "two"
    dialog._move(-1)
    assert [i.display_name for i in dialog.playlist.items] == ["two", "one"]

    built = []
    dialog.play_requested.connect(built.append)
    dialog._play()
    assert len(built) == 1
    assert len([e for e in built[0].events if e.kind == "key"]) == 2


def test_flow_builder_gate_shows_on_node(qtbot, tmp_path):
    import base64

    one = tmp_path / "one.tmacc"
    _write(one, "a")
    dialog = FlowBuilderDialog(MacroLibrary(), docked=False)
    qtbot.addWidget(dialog)
    dialog._add_path(str(one))
    png = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )).decode("ascii")
    dialog.playlist.set_gate(0, png)
    dialog._rebuild_scene()
    assert dialog._nodes[1].gate_pixmap is not None
    assert "gated" in dialog._nodes[1].subtitle
