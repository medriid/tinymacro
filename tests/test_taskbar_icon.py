"""The frameless windows must keep a real taskbar icon on every show path.

Studio shows itself maximized as its first native show — a path where Windows
otherwise never receives WM_SETICON — so the base window re-asserts the icon on
the native handle in showEvent. These tests pin that behaviour and the
process-identity helper that makes Windows use our icon at all.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.gui.framed_window import FramelessWindow
from tinymacro.gui.icons import APP_USER_MODEL_ID, app_icon, set_app_user_model_id


def test_set_app_user_model_id_is_safe_to_call():
    # No-op off Windows, real call on Windows — either way it must never raise.
    set_app_user_model_id()
    assert isinstance(APP_USER_MODEL_ID, str) and APP_USER_MODEL_ID


def test_app_icon_is_not_empty():
    icon = app_icon()
    assert not icon.isNull()
    assert icon.availableSizes(), "app icon should expose concrete pixmap sizes"


def test_window_reasserts_icon_on_show(qtbot):
    window = FramelessWindow("Tiny Macro — Test")
    qtbot.addWidget(window)
    assert not window.windowIcon().isNull()

    window.show()
    qtbot.waitExposed(window)

    handle = window.windowHandle()
    assert handle is not None
    assert not handle.icon().isNull()


def test_window_keeps_icon_when_shown_maximized(qtbot):
    # Mirrors Studio's show() override, the case that originally lost the icon.
    window = FramelessWindow("Tiny Macro — Studio")
    qtbot.addWidget(window)

    window.showMaximized()
    qtbot.waitExposed(window)

    handle = window.windowHandle()
    assert handle is not None
    assert not handle.icon().isNull()
