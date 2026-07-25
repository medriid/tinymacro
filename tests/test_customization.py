from __future__ import annotations

import pytest

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings


def test_ui_scale_and_density_round_trip():
    s = Settings()
    s.ui_scale = 1.3
    s.density = "compact"
    restored = Settings.from_dict(s.to_dict())
    assert restored.ui_scale == 1.3
    assert restored.density == "compact"


def test_invalid_ui_scale_rejected():
    s = Settings()
    s.ui_scale = 5.0
    with pytest.raises(ValueError):
        s.validate()


def test_invalid_density_rejected():
    s = Settings()
    s.density = "roomy"
    with pytest.raises(ValueError):
        s.validate()


def test_per_macro_speed_and_loop_persist():
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")], speed=2.5, loop_count=7)
    restored = Macro.from_dict(macro.to_dict())
    assert restored.speed == 2.5
    assert restored.loop_count == 7


def test_macro_defaults_speed_loop_for_old_files():
    old = {
        "format": "tiny-macro",
        "version": 2,
        "events": [{"timestamp_ns": 0, "kind": "key", "action": "press", "key": "a"}],
    }
    macro = Macro.from_dict(old)
    assert macro.speed == 1.0
    assert macro.loop_count == 1
