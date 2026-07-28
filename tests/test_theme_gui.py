from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from PyQt6.QtWidgets import QApplication

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.settings import Settings
from tinymacro.core.theme_pack import Background, Theme
from tinymacro.gui.main_window import MainWindow
from tinymacro.gui.theme import apply_theme, current_theme
from tinymacro.gui.theme_editor import ThemeEditor


def _png_bytes(w=64, h=48) -> bytes:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.fillRect(img.rect(), QColor("#3366cc"))
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def test_settings_active_theme_round_trip():
    s = Settings()
    s.active_theme = "/some/path/my.tmactheme"
    assert Settings.from_dict(s.to_dict()).active_theme == "/some/path/my.tmactheme"


def test_apply_image_theme_installs_background(qtbot, tmp_path):
    theme = Theme(name="Img", background=Background(kind="image", asset="bg", fit="cover", scrim=0.2),
                  panel_opacity=0.7)
    theme.set_asset("bg", _png_bytes())
    path = tmp_path / "img.tmactheme"
    theme.save(path)

    settings = Settings(backend="fake", onboarding_seen=True, animations=False, active_theme=str(path))
    apply_theme(QApplication.instance(), settings)  # app.py applies the theme before building windows
    win = MainWindow(settings, FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.show()
    assert current_theme() is not None
    assert win._themed_bg is not None  # image background installed

    # Switching to default removes it.
    settings.active_theme = ""
    apply_theme(QApplication.instance(), settings)
    win._refresh_themed_background()
    assert win._themed_bg is None


def test_theme_editor_save_and_use(qtbot, tmp_path, monkeypatch):
    from tinymacro.core import theme_pack

    monkeypatch.setattr(theme_pack, "default_themes_dir", lambda: tmp_path)
    monkeypatch.setattr("tinymacro.gui.theme_editor.default_themes_dir", lambda: tmp_path)

    settings = Settings(backend="fake")
    persisted = []
    editor = ThemeEditor(settings, persist=lambda: persisted.append(1))
    qtbot.addWidget(editor)
    # Default is a solid theme; Save & Use should activate it.
    editor.name.setText("Neon")
    editor._save_and_use()
    assert settings.active_theme.endswith(".tmactheme")
    assert persisted == [1]
    # The saved file loads back.
    loaded = Theme.load(settings.active_theme)
    assert loaded.name == "Neon"


_GIF = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;"


def test_animated_theme_installs_and_pauses(qtbot, tmp_path):
    theme = Theme(name="Anim", background=Background(kind="animated", asset="g", fps_cap=20))
    theme.set_asset("g", _GIF)
    path = tmp_path / "anim.tmactheme"
    theme.save(path)

    settings = Settings(backend="fake", onboarding_seen=True, animations=True, active_theme=str(path))
    apply_theme(QApplication.instance(), settings)
    win = MainWindow(settings, FakeBackend(), persist_settings=False)
    qtbot.addWidget(win)
    win.show()
    assert win._themed_bg is not None
    # Pausing/resuming the GIF must not raise.
    win._themed_bg.set_paused(True)
    win._themed_bg.set_paused(False)
    settings.active_theme = ""
    apply_theme(QApplication.instance(), settings)


def test_theme_editor_use_default_clears(qtbot):
    settings = Settings(backend="fake", active_theme="/x/y.tmactheme")
    editor = ThemeEditor(settings, persist=lambda: None)
    qtbot.addWidget(editor)
    editor._use_default()
    assert settings.active_theme == ""


def test_theme_editor_export_import_round_trip(qtbot, tmp_path):
    settings = Settings(backend="fake")
    editor = ThemeEditor(settings, persist=lambda: None)
    qtbot.addWidget(editor)
    editor.name.setText("Portable")
    editor.accent.set_color("#ff0000")
    theme = editor._build_theme()
    assert theme is not None
    out = tmp_path / "portable.tmactheme"
    theme.save(out)

    editor2 = ThemeEditor(Settings(backend="fake"), persist=lambda: None)
    qtbot.addWidget(editor2)
    editor2._load_into_controls(Theme.load(out))
    assert editor2.name.text() == "Portable"
    assert editor2.accent.color().lower() == "#ff0000"
