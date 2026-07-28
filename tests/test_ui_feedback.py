"""Interaction polish: default button colours, sounds, fonts, transport row."""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.settings import Settings
from tinymacro.core.theme_pack import (
    DEFAULT_BUTTON_COLORS,
    Background,
    Theme,
    resolve_button_color,
)
from tinymacro.gui import theme as theme_mod
from tinymacro.gui.sounds import UiSounds, ui_sounds
from tinymacro.gui.studio_window import StudioWindow


# -- default per-button colours ----------------------------------------------
def test_transport_defaults_are_orange_green_red():
    assert DEFAULT_BUTTON_COLORS["record"].lower() == "#e8833a"
    assert DEFAULT_BUTTON_COLORS["play"].lower() == "#35b87a"
    assert DEFAULT_BUTTON_COLORS["stop"].lower() == "#e0554e"
    assert "pause" in DEFAULT_BUTTON_COLORS


def test_resolve_button_color_precedence():
    # No theme → built-in default.
    assert resolve_button_color(None, "record", "#888888") == DEFAULT_BUTTON_COLORS["record"]
    # Unknown button → caller's fallback.
    assert resolve_button_color(None, "library", "#888888") == "#888888"
    # A custom theme still wins over the built-in default.
    theme = Theme(background=Background(kind="solid", color="#101010"),
                  button_colors={"record": "#123456"})
    assert resolve_button_color(theme, "record", "#888888") == "#123456"
    # …but only for the buttons it overrides.
    assert resolve_button_color(theme, "play", "#888888") == DEFAULT_BUTTON_COLORS["play"]


# -- Studio transport row -----------------------------------------------------
def _studio(qtbot):
    win = StudioWindow(Settings(onboarding_seen=True, animations=False),
                       FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    return win


def test_studio_transport_is_icon_only_with_tooltips(qtbot):
    win = _studio(qtbot)
    for button, tip in ((win.record_btn, "Record"), (win.play_btn, "Play"), (win.pause_btn, "Pause")):
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert button.text() == ""       # labels dropped so all three fit one row
        assert button.toolTip() == tip   # the label lives in the tooltip instead


def test_studio_transport_shares_one_row(qtbot):
    win = _studio(qtbot)
    win.showNormal()
    qtbot.waitExposed(win)
    # Same row => same vertical position, increasing x.
    tops = {b.mapTo(win, b.rect().topLeft()).y() for b in (win.record_btn, win.play_btn, win.pause_btn)}
    assert len(tops) == 1
    xs = [b.mapTo(win, b.rect().topLeft()).x() for b in (win.record_btn, win.play_btn, win.pause_btn)]
    assert xs == sorted(xs)


def test_studio_transport_stays_dynamic(qtbot):
    win = _studio(qtbot)
    win.player.state.playing = True
    win._update_state()
    assert win.play_btn.toolTip() == "Stop"    # Play↔Stop toggle survives the rework
    assert win.pause_btn.isEnabled()
    win.player.state.paused = True
    win._update_state()
    assert win.pause_btn.toolTip() == "Resume"  # Pause↔Resume too
    win.player.state.playing = win.player.state.paused = False


def test_studio_transport_uses_theme_button_colors(qtbot):
    win = _studio(qtbot)
    assert win._button_color("record") == DEFAULT_BUTTON_COLORS["record"]
    assert win._button_color("play") == DEFAULT_BUTTON_COLORS["play"]


# -- sounds -------------------------------------------------------------------
def test_ui_sounds_is_a_singleton():
    assert ui_sounds() is ui_sounds()


def test_sound_assets_are_present():
    from tinymacro.gui.sounds import SOUND_DIR

    assert (SOUND_DIR / "hover.wav").is_file()
    assert (SOUND_DIR / "click.wav").is_file()


def test_disabled_sounds_never_play():
    played: list[str] = []

    class _Recording(UiSounds):
        def _effect(self, name):  # noqa: D102 - capture instead of loading audio
            played.append(name)
            return None

    sounds = _Recording()
    sounds.set_enabled(False)
    sounds.hover()
    sounds.click()
    assert played == []

    sounds.set_enabled(True)
    sounds.click()
    assert played == ["click"]


def test_hover_sound_is_throttled():
    played: list[str] = []

    class _Recording(UiSounds):
        def _effect(self, name):
            played.append(name)
            return None

    sounds = _Recording()
    for _ in range(10):  # a fast pointer sweep must not machine-gun the speaker
        sounds.hover()
    assert len(played) == 1


def test_settings_ui_sounds_round_trip():
    s = Settings()
    assert s.ui_sounds is True  # on by default
    s.ui_sounds = False
    assert Settings.from_dict(s.to_dict()).ui_sounds is False


# -- hover tint on Classic's toolbar -----------------------------------------
def _hover(app, widget) -> None:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QEnterEvent

    app.sendEvent(widget, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))


def _leave(app, widget) -> None:
    from PyQt6.QtCore import QEvent

    app.sendEvent(widget, QEvent(QEvent.Type.Leave))


def test_toolbar_button_tints_with_its_own_colour(qtbot):
    from PyQt6.QtWidgets import QApplication

    from tinymacro.gui.main_window import MainWindow

    win = MainWindow(Settings(backend="fake", onboarding_seen=True, animations=False),
                     FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    app = QApplication.instance()

    button = win.toolbar.widgetForAction(win.record_action)
    base = button.styleSheet()
    _hover(app, button)
    # Record hovers orange, and the tint is fully removed again on leave.
    assert DEFAULT_BUTTON_COLORS["record"].lower() in button.styleSheet().lower()
    _leave(app, button)
    assert button.styleSheet() == base


def test_hover_state_survives_fresh_widget_wrappers(qtbot):
    """Regression: state must not be keyed by id() of a PyQt wrapper.

    ``widgetForAction`` returns a new Python wrapper each call; those are
    garbage-collected and their id()s recycled, so an id-keyed dict silently
    loses (or cross-links) entries.
    """
    from PyQt6.QtWidgets import QApplication

    from tinymacro.gui.main_window import MainWindow

    from tinymacro.core.events import MacroEvent
    from tinymacro.core.macro import Macro

    win = MainWindow(Settings(backend="fake", onboarding_seen=True, animations=False),
                     FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    app = QApplication.instance()
    # Play only tints while it's enabled (a disabled button must stay inert).
    win.macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    win._update_state()

    for action, expected in ((win.record_action, "record"), (win.play_action, "play")):
        fresh = win.toolbar.widgetForAction(action)  # a brand-new wrapper object
        _hover(app, fresh)
        assert win._button_color(expected).lower() in fresh.styleSheet().lower()
        _leave(app, fresh)


def test_disabled_button_does_not_tint(qtbot):
    from PyQt6.QtWidgets import QApplication

    from tinymacro.gui.main_window import MainWindow

    win = MainWindow(Settings(backend="fake", onboarding_seen=True, animations=False),
                     FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    app = QApplication.instance()

    button = win.toolbar.widgetForAction(win.play_action)
    assert not button.isEnabled()  # nothing recorded yet
    _hover(app, button)
    assert button.styleSheet() == ""  # stays inert while disabled


def test_pin_button_keeps_its_own_stylesheet(qtbot):
    from PyQt6.QtWidgets import QApplication

    from tinymacro.gui.main_window import MainWindow

    win = MainWindow(Settings(backend="fake", onboarding_seen=True, animations=False),
                     FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    app = QApplication.instance()

    before = win.top_button.styleSheet()
    assert "checked" in before  # the pin styles its own checked state
    _hover(app, win.top_button)
    _leave(app, win.top_button)
    assert win.top_button.styleSheet() == before  # hover must not clobber it


# -- fonts --------------------------------------------------------------------
def test_font_stack_prefers_crafted_faces_over_os_defaults():
    stack = theme_mod.UI_FONT_STACK
    assert stack.index('"Inter"') < stack.index('"Segoe UI"')
    assert stack.rstrip().endswith("sans-serif")


def test_load_bundled_fonts_is_safe_without_font_files(qtbot):
    # The folder ships without any TTF committed; loading must be a no-op, and
    # never raise, so the app falls back to the system stack.
    assert isinstance(theme_mod.load_bundled_fonts(), list)
