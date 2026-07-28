from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings
from tinymacro.core.theme_pack import DEFAULT_BUTTON_COLORS, Background, Theme
from tinymacro.gui.color_picker import ColorPickerDialog
from tinymacro.gui.main_window import MainWindow
from tinymacro.gui.studio_window import StudioWindow
from tinymacro.gui.theme import apply_theme


def _classic(qtbot):
    win = MainWindow(Settings(backend="fake", onboarding_seen=True), FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    return win


def test_color_picker_hex_and_rgb_sync(qtbot):
    dlg = ColorPickerDialog("#4f9dde")
    qtbot.addWidget(dlg)
    assert dlg.color_hex() == "#4f9dde"

    dlg.hex.setText("#ff0000")
    dlg._from_hex()
    assert dlg.color_hex() == "#ff0000"
    assert (dlg.r.value(), dlg.g.value(), dlg.b.value()) == (255, 0, 0)

    dlg.r.setValue(0)
    dlg.g.setValue(255)
    dlg.b.setValue(0)
    dlg._from_rgb()
    assert dlg.color_hex() == "#00ff00"


def test_classic_hides_title_label_studio_keeps_it(qtbot):
    win = _classic(qtbot)
    assert win.title_bar._show_title is False  # Classic: redundant next to the menu

    studio = StudioWindow(Settings(onboarding_seen=True), FakeBackend(), persist_settings=False)
    qtbot.addWidget(studio)
    assert studio.title_bar._show_title is True


def test_play_button_is_dynamic(qtbot):
    win = _classic(qtbot)
    win.macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    win._update_state()
    assert win.play_action.toolTip() == "Play"
    win.player.state.playing = True
    win._update_state()
    assert win.play_action.toolTip() == "Stop"
    win.player.state.playing = False


def test_pin_button_reflects_state(qtbot):
    win = _classic(qtbot)
    win.top_action.setChecked(True)
    win._update_pin_button()
    assert "on" in win.top_action.toolTip()
    win.top_action.setChecked(False)
    win._update_pin_button()
    assert "off" in win.top_action.toolTip()


def test_three_transport_buttons_classic(qtbot):
    win = _classic(qtbot)
    win.macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    win.player.state.playing = True
    win._update_state()
    assert win.play_action.toolTip() == "Stop"  # play = play/stop toggle
    assert win.pause_action.isEnabled()          # pause is its own button
    assert win.pause_action.toolTip() == "Pause"
    win.player.state.paused = True
    win._update_state()
    assert win.pause_action.toolTip() == "Resume"
    win.player.state.playing = False
    win.player.state.paused = False


def test_studio_has_record_play_pause(qtbot):
    studio = StudioWindow(Settings(onboarding_seen=True), FakeBackend(), persist_settings=False)
    qtbot.addWidget(studio)
    assert hasattr(studio, "record_btn")
    assert hasattr(studio, "play_btn")
    assert hasattr(studio, "pause_btn")


def test_docs_dialog_categories(qtbot):
    from tinymacro.gui.docs_dialog import CATEGORIES, DocsDialog

    dlg = DocsDialog()
    qtbot.addWidget(dlg)
    assert dlg.list.count() == len(CATEGORIES)
    dlg.list.setCurrentRow(2)
    assert dlg.heading.text() == CATEGORIES[2][0]
    assert "coming soon" in dlg.body.text().lower()


def test_button_color_uses_theme_override(qtbot, tmp_path):
    theme = Theme(name="Btn", background=Background(kind="solid", color="#101010"),
                  button_colors={"play": "#123456"})
    path = tmp_path / "btn.tmactheme"
    theme.save(path)
    from PyQt6.QtWidgets import QApplication

    settings = Settings(backend="fake", onboarding_seen=True, active_theme=str(path))
    apply_theme(QApplication.instance(), settings)
    win = MainWindow(settings, FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    assert win._button_color("play") == "#123456"  # theme override wins
    # No override → the built-in transport default (record is orange).
    assert win._button_color("record") == DEFAULT_BUTTON_COLORS["record"]
    # A button with neither an override nor a default falls back to the icon tint.
    assert win._button_color("open") == win._icon_color()
    # Reset global theme for other tests.
    settings.active_theme = ""
    apply_theme(QApplication.instance(), settings)
