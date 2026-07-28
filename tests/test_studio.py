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
from tinymacro.gui.studio_window import DockArea, StudioWindow
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
    dpr = win.dock.inner.devicePixelRatioF()
    assert isinstance(region, DockRegion)
    # The aperture is reported in physical pixels (logical size × device ratio).
    assert region.width == round(win.dock.inner.width() * dpr)
    assert region.height == round(win.dock.inner.height() * dpr)
    assert region.width > 500
    assert region.height > 400


def test_dock_region_scales_with_device_pixel_ratio(qtbot, monkeypatch):
    # On a scaled display the aperture is reported in physical pixels, so the
    # docked window (placed via physical-pixel SetWindowPos) fills it.
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.resize(1160, 660)
    win.show()
    inner = win.dock.inner
    monkeypatch.setattr(inner, "devicePixelRatioF", lambda: 1.25)
    region = win.dock.region()
    assert region.width == round(inner.width() * 1.25)
    assert region.height == round(inner.height() * 1.25)


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


def test_studio_opens_maximized(qtbot):
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.show()
    assert win.isMaximized()


def test_titlebar_max_restore_icon_swaps(qtbot):
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.title_bar.update_max_restore(True)
    assert win.title_bar.btn_max.toolTip() == "Restore"
    win.title_bar.update_max_restore(False)
    assert win.title_bar.btn_max.toolTip() == "Maximize"


class _RestoreBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.moves: list[tuple[int, int, int, int, int]] = []

    def supports_docking(self) -> bool:
        return True

    def window_client_rect(self, handle: int):
        return (100, 200, 800, 600)

    def move_resize_window(self, handle: int, left: int, top: int, width: int, height: int) -> bool:
        self.moves.append((handle, left, top, width, height))
        return True


def test_undock_restores_window_geometry(qtbot):
    backend = _RestoreBackend()
    win = StudioWindow(Settings(), backend, persist_settings=False)
    qtbot.addWidget(win)
    win._target_hwnd = 55
    win._pre_dock_rect = (100, 200, 800, 600)
    win.settings.restore_window_on_undock = True
    win._undock()
    assert (55, 100, 200, 800, 600) in backend.moves
    assert win._target_hwnd is None
    assert win._pre_dock_rect is None


def test_dock_area_letterboxes_to_aspect(qtbot):
    area = DockArea()
    qtbot.addWidget(area)
    area.resize(1000, 1000)

    area.set_aspect_ratio(None)  # free fills the whole area
    assert (area.inner.width(), area.inner.height()) == (1000, 1000)

    area.set_aspect_ratio(16 / 9)  # tall area → limited by width, centred vertically
    assert area.inner.width() == 1000
    assert area.inner.height() == round(1000 * 9 / 16)
    assert area.inner.x() == 0
    assert area.inner.y() == (1000 - area.inner.height()) // 2

    area.resize(1600, 500)  # wide area → limited by height, centred horizontally
    area.set_aspect_ratio(16 / 9)
    assert area.inner.height() == 500
    assert area.inner.width() == round(500 * 16 / 9)
    assert area.inner.y() == 0
    assert area.inner.x() == (1600 - area.inner.width()) // 2


def test_studio_aspect_ratio_resolves_by_mode(qtbot):
    win = StudioWindow(Settings(studio_aspect="16:9"), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    assert abs(win._aspect_ratio_value() - 16 / 9) < 1e-9
    win.settings.studio_aspect = "free"
    assert win._aspect_ratio_value() is None
    win.settings.studio_aspect = "match"
    assert win._aspect_ratio_value() is None  # no target docked yet
    win._pre_dock_rect = (0, 0, 1000, 500)
    assert abs(win._aspect_ratio_value() - 2.0) < 1e-9


def test_studio_aspect_combo_applies(qtbot):
    win = StudioWindow(Settings(), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.show()
    win.aspect_combo.setCurrentIndex(1)  # "16:9"
    assert win.settings.studio_aspect == "16:9"
    assert win.dock._ratio is not None


def test_undock_skips_restore_when_disabled(qtbot):
    backend = _RestoreBackend()
    win = StudioWindow(Settings(), backend, persist_settings=False)
    qtbot.addWidget(win)
    win._target_hwnd = 55
    win._pre_dock_rect = (100, 200, 800, 600)
    win.settings.restore_window_on_undock = False
    win._undock()
    assert backend.moves == []
