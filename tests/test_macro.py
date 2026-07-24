from __future__ import annotations

import json

import pytest

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro


def test_macro_roundtrip_and_normalization(tmp_path):
    macro = Macro(
        events=[
            MacroEvent(2_000, "key", "release", key="a"),
            MacroEvent(1_000, "key", "press", key="a"),
        ],
        backend="fake",
        screen_geometry="1920x1080",
        keyboard_layout="us",
        name="Demo",
    )
    path = tmp_path / "demo.tmacro"
    macro.save(path)

    loaded = Macro.load(path)

    assert loaded.name == "Demo"
    assert loaded.backend == "fake"
    assert [event.timestamp_ns for event in loaded.events] == [0, 1_000]
    assert json.loads(path.read_text())["format"] == "tiny-macro"


def test_trim_and_scale_timing():
    macro = Macro(
        events=[
            MacroEvent(1_000, "mouse", "move", x=1, y=1),
            MacroEvent(3_000, "mouse", "press", button="left", x=1, y=1),
            MacroEvent(9_000, "mouse", "release", button="left", x=1, y=1),
        ]
    ).normalized()

    trimmed = macro.trim_range(2_000, 9_000)
    scaled = trimmed.scale_timing(2)

    assert [event.timestamp_ns for event in trimmed.events] == [0, 6_000]
    assert [event.timestamp_ns for event in scaled.events] == [0, 12_000]


def test_invalid_macro_format_rejected():
    with pytest.raises(ValueError):
        Macro.from_dict({"format": "other", "events": []})


def test_legacy_wayland_mouse_button_key_is_repaired():
    macro = Macro.from_dict(
        {
            "format": "tiny-macro",
            "version": 1,
            "metadata": {"backend": "wayland-evdev"},
            "events": [
                {
                    "timestamp_ns": 100,
                    "kind": "key",
                    "action": "press",
                    "key": "('left', 'mouse')",
                }
            ],
        }
    )

    assert macro.events[0].kind == "mouse"
    assert macro.events[0].button == "left"
    assert macro.events[0].key is None
