from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from tinymacro.core.vision import (
    VISION_AVAILABLE,
    Match,
    decode_png,
    encode_png,
    match_in_image,
    match_template,
)


def _textured(width: int, height: int, seed: int) -> "np.ndarray":
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def test_vision_available():
    assert VISION_AVAILABLE


def test_locates_pasted_template():
    haystack = _textured(400, 300, seed=1)
    needle = _textured(40, 30, seed=99)
    haystack[80:110, 120:160] = needle  # paste at (x=120, y=80)

    match = match_in_image(haystack, needle, confidence=0.9, grayscale=False)
    assert match is not None
    # center of the pasted region
    assert abs(match.x - 140) <= 1
    assert abs(match.y - 95) <= 1
    assert match.score > 0.95


def test_absent_template_returns_none():
    haystack = _textured(300, 200, seed=2)
    needle = _textured(30, 30, seed=12345)  # unrelated, not present
    assert match_in_image(haystack, needle, confidence=0.9, grayscale=False) is None


def test_oversized_template_returns_none():
    haystack = _textured(50, 50, seed=3)
    needle = _textured(100, 100, seed=4)
    assert match_in_image(haystack, needle, confidence=0.5) is None


def test_png_round_trip_and_match():
    haystack = _textured(200, 150, seed=5)
    needle = _textured(24, 24, seed=77)
    haystack[50:74, 60:84] = needle
    match = match_template(encode_png(haystack), encode_png(needle), confidence=0.9, grayscale=False)
    assert isinstance(match, Match)
    assert abs(match.x - 72) <= 1 and abs(match.y - 62) <= 1


def test_decode_bad_bytes_raises():
    with pytest.raises(ValueError):
        decode_png(b"not-a-png")
