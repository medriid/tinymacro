from __future__ import annotations

import json

import pytest

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import (
    CLASSIC_EXTENSION,
    DOCK_EXTENSION,
    DOCK_FORMAT,
    LEGACY_CLASSIC_EXTENSION,
    Macro,
)


def test_extensions_pair_up():
    assert CLASSIC_EXTENSION == ".tmacc"
    assert DOCK_EXTENSION == ".tmacd"
    assert LEGACY_CLASSIC_EXTENSION == ".tmacro"


def test_legacy_tmacro_still_loads(tmp_path):
    legacy = tmp_path / "old.tmacro"
    Macro(events=[MacroEvent(0, "key", "press", key="a")]).save(legacy)
    # Extension isn't enforced on load; the format field is what matters.
    assert Macro.load(legacy).docked is False


def test_dock_macro_format_id():
    macro = Macro(events=[MacroEvent(0, "mouse", "press", button="left", x=1, y=2, fx=0.5, fy=0.5)],
                  docked=True, target_window="Roblox")
    data = macro.to_dict()
    assert data["format"] == DOCK_FORMAT
    assert data["metadata"]["docked"] is True
    assert data["metadata"]["target_window"] == "Roblox"


def test_dock_macro_round_trip():
    macro = Macro(events=[MacroEvent(0, "mouse", "press", button="left", x=1, y=2, fx=0.25, fy=0.75)],
                  docked=True, target_window="Notepad")
    restored = Macro.from_dict(json.loads(json.dumps(macro.to_dict())))
    assert restored.docked is True
    assert restored.target_window == "Notepad"
    assert restored.events[0].fx == 0.25


def test_classic_macro_stays_classic():
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    assert macro.to_dict()["format"] == "tiny-macro"
    assert Macro.from_dict(macro.to_dict()).docked is False


def test_load_for_variant_rejects_mismatch(tmp_path):
    classic_path = tmp_path / "a.tmacro"
    Macro(events=[MacroEvent(0, "key", "press", key="a")]).save(classic_path)
    dock_path = tmp_path / "b.tmacd"
    Macro(events=[MacroEvent(0, "mouse", "press", button="left", fx=0.5, fy=0.5)],
          docked=True).save(dock_path)

    # Correct variant loads fine.
    assert Macro.load_for_variant(classic_path, docked=False).docked is False
    assert Macro.load_for_variant(dock_path, docked=True).docked is True

    # Wrong variant is rejected both ways.
    with pytest.raises(ValueError):
        Macro.load_for_variant(dock_path, docked=False)
    with pytest.raises(ValueError):
        Macro.load_for_variant(classic_path, docked=True)
