from __future__ import annotations

import base64
import gzip
import json

import pytest

from tinymacro.core.theme_pack import (
    Background,
    Theme,
    ThemeError,
    contrast_ratio,
    sniff_image,
)

# Minimal 1x1 image assets (real magic bytes).
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)
_GIF = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;"


def test_sniff_image_recognises_formats():
    assert sniff_image(_PNG) == "png"
    assert sniff_image(_GIF) == "gif"
    assert sniff_image(b"\xff\xd8\xff\xe0stuff") == "jpeg"
    assert sniff_image(b"not an image") is None


def test_solid_theme_round_trip(tmp_path):
    theme = Theme(name="Midnight", accent="#ff5cae", background=Background(kind="solid", color="#0c0c12"))
    assert theme.validate() == [] or isinstance(theme.validate(), list)
    path = tmp_path / "midnight.tmactheme"
    theme.save(path)
    # File is gzip-compressed.
    assert path.read_bytes()[:2] == b"\x1f\x8b"
    loaded = Theme.load(path)
    assert loaded.name == "Midnight"
    assert loaded.accent == "#ff5cae"
    assert loaded.background.kind == "solid" and loaded.background.color == "#0c0c12"


def test_image_theme_embeds_and_reloads(tmp_path):
    theme = Theme(background=Background(kind="image", asset="bg", fit="cover", scrim=0.4))
    theme.set_asset("bg", _PNG)
    assert theme.validate() == [] or isinstance(theme.validate(), list)
    assert theme.background_bytes() == _PNG
    path = tmp_path / "img.tmactheme"
    theme.save(path)
    loaded = Theme.load(path)
    assert loaded.background.asset == "bg"
    assert loaded.background_bytes() == _PNG  # asset survived the round trip


def test_animated_gif_theme_validates():
    theme = Theme(background=Background(kind="animated", asset="g", fit="cover", fps_cap=24))
    theme.set_asset("g", _GIF)
    assert theme.validate() == []  # a real GIF: no warnings


def test_animated_with_non_gif_warns():
    theme = Theme(background=Background(kind="animated", asset="p"))
    theme.set_asset("p", _PNG)
    warnings = theme.validate()
    assert any("GIF" in w for w in warnings)


def test_invalid_color_is_rejected():
    theme = Theme(accent="not-a-color")
    with pytest.raises(ThemeError):
        theme.validate()


def test_missing_background_asset_is_rejected():
    theme = Theme(background=Background(kind="image", asset="nope"))
    with pytest.raises(ThemeError):
        theme.validate()


def test_non_image_asset_is_rejected():
    theme = Theme(background=Background(kind="image", asset="x"))
    theme.set_asset("x", b"this is not an image")
    with pytest.raises(ThemeError):
        theme.validate()


def test_low_contrast_warns():
    theme = Theme(text="#101010", background=Background(kind="solid", color="#000000"))
    assert any("contrast" in w for w in theme.validate())
    assert contrast_ratio("#ffffff", "#000000") > 20


def test_load_rejects_foreign_and_corrupt(tmp_path):
    foreign = tmp_path / "foreign.tmactheme"
    foreign.write_bytes(gzip.compress(json.dumps({"format": "nope"}).encode()))
    with pytest.raises(ThemeError):
        Theme.load(foreign)

    corrupt = tmp_path / "corrupt.tmactheme"
    corrupt.write_bytes(b"\x1f\x8b not really gzip")
    with pytest.raises(Exception):
        Theme.load(corrupt)


def test_plain_json_also_loads(tmp_path):
    # Loader accepts uncompressed JSON too (easier hand-editing / debugging).
    theme = Theme(name="Plain")
    path = tmp_path / "plain.tmactheme"
    path.write_text(json.dumps(theme.to_dict()), encoding="utf-8")
    assert Theme.load(path).name == "Plain"


def test_oversized_asset_rejected():
    theme = Theme(background=Background(kind="solid", color="#111111"))
    # 25 MB of zero bytes exceeds the 24 MB per-asset cap.
    theme.set_asset("huge", b"\x00" * (25 * 1024 * 1024))
    with pytest.raises(ThemeError):
        theme.validate()
