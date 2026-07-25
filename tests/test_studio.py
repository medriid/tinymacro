from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.dock import DockRegion
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import DOCK_EXTENSION, Macro
from tinymacro.core.settings import Settings
from tinymacro.gui.anim import AnimatedToolButton
from tinymacro.gui.framed_window import FramelessWindow
from tinymacro.gui.studio_window import StudioWindow
from tinymacro.gui.window_picker import WindowPicker


def test_frameless_window_has_titlebar(qtbot):
    win = FramelessWindow("Test", animated=False)
    qtbot.addWidget(win)
    assert win.title_bar.height() == 40
    assert win.menu_bar() is not None


def test_animated_button_glow(qtbot):
    button = AnimatedToolButton(animated=False)
    qtbot.addWidget(button)
    button.set_glow(1.0)
    assert button.get_glow() == 1.0


def test_studio_constructs_and_dock_region(qtbot):
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.resize(1160, 660)
    win.show()
    region = win.dock.region()
    assert isinstance(region, DockRegion)
    # 16:9 inner frame
    assert abs(region.aspect_ratio - 16 / 9) < 0.05


def test_studio_makes_dock_macros(qtbot, tmp_path):
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win._target_title = "Roblox"
    win.macro = Macro(events=[MacroEvent(0, "mouse", "press", button="left", fx=0.5, fy=0.5)])
    path = tmp_path / "m.tmacd"
    win.macro = win.macro.copy_with(docked=True, target_window="Roblox")
    win.macro.save(path)
    reloaded = Macro.load_for_variant(path, docked=True)
    assert reloaded.docked is True and reloaded.target_window == "Roblox"


def test_window_picker_empty_on_fake_backend(qtbot):
    picker = WindowPicker(FakeBackend())
    qtbot.addWidget(picker)
    assert picker.list.count() == 0  # fake backend lists no windows


def test_studio_switch_signal(qtbot):
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    received = []
    win.switch_variant_requested.connect(received.append)
    win._go_classic()
    assert received == ["classic"]
    assert win.settings.ui_variant == "classic"


def test_dock_extension():
    assert DOCK_EXTENSION == ".tmacd"
