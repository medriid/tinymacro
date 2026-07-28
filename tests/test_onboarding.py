from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow
from tinymacro.gui.onboarding import OnboardingOverlay, OnboardingStep


def _host(qtbot):
    win = QMainWindow()
    body = QWidget()
    lay = QVBoxLayout(body)
    a, b = QPushButton("A"), QPushButton("B")
    lay.addWidget(a)
    lay.addWidget(b)
    win.setCentralWidget(body)
    win.resize(600, 400)
    qtbot.addWidget(win)
    win.show()
    return win, a, b


def test_overlay_navigation_and_finish(qtbot):
    win, a, b = _host(qtbot)
    steps = [
        OnboardingStep("Welcome", "Intro, no spotlight."),
        OnboardingStep("A", "First control.", lambda: a),
        OnboardingStep("B", "Second control.", lambda: b),
    ]
    seen = []
    overlay = OnboardingOverlay(win, steps, animated=False)
    qtbot.addWidget(overlay)
    overlay.finished.connect(lambda: seen.append(1))
    overlay.start()

    assert overlay._index == 0
    assert overlay._spot_rect.isNull()  # intro has no spotlight
    assert overlay._blurred is not None and overlay._sharp is not None

    overlay._next()
    assert overlay._index == 1
    assert not overlay._spot_rect.isNull()  # spotlight over button A

    overlay._back()
    assert overlay._index == 0

    overlay._next()
    overlay._next()  # to last step (B)
    assert overlay._index == 2
    overlay._next()  # Finish
    assert seen == [1]


def test_overlay_skip_emits_finished_once(qtbot):
    win, a, _ = _host(qtbot)
    seen = []
    overlay = OnboardingOverlay(win, [OnboardingStep("A", "x", lambda: a)], animated=False)
    qtbot.addWidget(overlay)
    overlay.finished.connect(lambda: seen.append(1))
    overlay.start()
    overlay._skip()
    overlay._skip()  # idempotent
    assert seen == [1]


def test_first_run_marks_seen_after_finish(qtbot):
    persisted = []
    win = MainWindow(
        Settings(backend="fake", onboarding_seen=False, animations=False),
        FakeBackend(), persist_settings=True, on_persist=lambda: persisted.append(1),
    )
    qtbot.addWidget(win)
    win.show()
    win.start_onboarding(force=True)
    assert win._onboarding is not None
    win._onboarding._finish()
    assert win.settings.onboarding_seen is True
    assert win._onboarding is None


def test_onboarding_skipped_when_already_seen(qtbot):
    win = MainWindow(
        Settings(backend="fake", onboarding_seen=True, animations=False),
        FakeBackend(), persist_settings=False,
    )
    qtbot.addWidget(win)
    win.start_onboarding()  # not forced
    assert win._onboarding is None


def test_preferences_show_intro_emits_replay(qtbot):
    from tinymacro.gui.preferences import PreferencesDialog

    dlg = PreferencesDialog(Settings())
    qtbot.addWidget(dlg)
    seen = []
    dlg.replay_tour.connect(lambda: seen.append(1))
    dlg.show_intro_btn.click()
    assert seen == [1]


def test_settings_onboarding_round_trip():
    s = Settings()
    s.onboarding_seen = True
    assert Settings.from_dict(s.to_dict()).onboarding_seen is True
