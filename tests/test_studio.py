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
    assert region.width == win.dock.inner.width()
    assert region.height == win.dock.inner.height()
    assert region.width > 500
    assert region.height > 400


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


def test_studio_switch_persist_callback_is_no_arg(qtbot):
    calls = []
    win = StudioWindow(
        Settings(), FakeBackend(), persist_settings=True, on_persist=lambda: calls.append("saved")
    )
    qtbot.addWidget(win)
    win._go_classic()
    assert calls == ["saved"]


class _DockingBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.moves: list[tuple[int, int, int, int, int]] = []

    def move_resize_window(self, handle: int, left: int, top: int, width: int, height: int) -> bool:
        self.moves.append((handle, left, top, width, height))
        return True


def test_studio_tracks_exact_dock_aperture(qtbot):
    backend = _DockingBackend()
    win = StudioWindow(Settings(), backend, persist_settings=False)
    qtbot.addWidget(win)
    win.resize(1160, 660)
    win.show()
    win._target_hwnd = 123
    win._track_dock()
    region = win.dock.region()
    assert backend.moves[-1] == (123, region.left, region.top, region.width, region.height)


def test_dock_extension():
    assert DOCK_EXTENSION == ".tmacd"
