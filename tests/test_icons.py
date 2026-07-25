from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.gui.icons import app_icon, get_icon, icon_names, render_app_ico


def test_every_icon_renders_non_null(qtbot):
    for name in icon_names():
        icon = get_icon(name, "#000000")
        assert not icon.isNull(), name
        assert not icon.pixmap(20, 20).isNull(), name


def test_unknown_icon_raises(qtbot):
    with pytest.raises(KeyError):
        get_icon("does-not-exist", "#000000")


def test_icon_tint_changes_pixmap(qtbot):
    black = get_icon("play", "#000000").pixmap(20, 20).toImage()
    white = get_icon("play", "#ffffff").pixmap(20, 20).toImage()
    assert black != white


def test_app_icon_loads(qtbot):
    icon = app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()


def test_render_app_ico_is_multi_resolution(qtbot, tmp_path):
    import struct

    dest = render_app_ico(tmp_path / "app.ico", sizes=(16, 32, 48))
    assert dest.exists()
    data = dest.read_bytes()
    reserved, image_type, count = struct.unpack("<HHH", data[:6])
    assert reserved == 0 and image_type == 1  # valid ICO header
    assert count == 3  # every requested size present, not a single image
    dims = set()
    for i in range(count):
        entry = data[6 + 16 * i : 6 + 16 * i + 16]
        w, h = entry[0], entry[1]
        dims.add((w or 256, h or 256))
    assert dims == {(16, 16), (32, 32), (48, 48)}
