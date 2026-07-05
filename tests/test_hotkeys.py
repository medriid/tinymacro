from __future__ import annotations

import pytest

from tinymacro.core.hotkeys import Hotkey, HotkeySet


def test_hotkey_parse_matches_and_stringifies():
    hotkey = Hotkey.parse("Ctrl + Shift + Alt + R")

    assert hotkey.matches(["alt", "shift", "control", "r"])
    assert "R" in str(hotkey)


def test_hotkey_conflicts_are_rejected():
    hotkeys = HotkeySet(record=Hotkey.parse("f8"), play=Hotkey.parse("f8"))

    with pytest.raises(ValueError):
        hotkeys.validate()
