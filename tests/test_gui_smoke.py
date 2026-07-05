from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow


def test_main_window_initial_state(qtbot):
    window = MainWindow(Settings(backend="fake"), FakeBackend(), persist_settings=False)
    qtbot.addWidget(window)

    assert "Tiny Macro" in window.windowTitle()
    assert not window.play_action.isEnabled()
