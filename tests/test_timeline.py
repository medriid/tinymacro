from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.gui.timeline import TimelineWidget


def test_timeline_set_macro_resizes(qtbot):
    widget = TimelineWidget(kind_colors={"key": "#4f9dde"})
    qtbot.addWidget(widget)
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(2_000_000_000, "key", "press", key="b"),
    ])
    widget.set_zoom(100)
    widget.set_macro(macro)
    # ~2 seconds at 100 px/s → at least 200px of content
    assert widget.minimumWidth() >= 200


def test_timeline_click_emits_index(qtbot):
    widget = TimelineWidget()
    qtbot.addWidget(widget)
    widget.set_zoom(100)
    widget.set_macro(Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000_000, "key", "press", key="b"),
    ]))
    widget.resize(400, 80)

    received = []
    widget.event_clicked.connect(received.append)

    # Simulate a click near the second event (~x = 8 + 1.0s*100 = 108).
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(108, 20),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(ev)
    assert received == [1]


def test_timeline_selected_index(qtbot):
    widget = TimelineWidget()
    qtbot.addWidget(widget)
    widget.set_macro(Macro(events=[MacroEvent(0, "key", "press", key="a")]))
    widget.set_selected(0)  # should not raise; just repaints
    assert widget._selected == 0
