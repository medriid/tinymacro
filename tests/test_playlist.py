from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.playlist import Playlist, PlaylistItem


def _macro(*offsets_ms: int) -> Macro:
    events = [MacroEvent(ms * 1_000_000, "key", "press", key="a") for ms in offsets_ms]
    return Macro(events=events)


def test_build_chains_in_order_with_gap():
    a = _macro(0, 100)   # duration 100ms
    b = _macro(0, 50)    # duration 50ms
    lib = {"a.tmacc": a, "b.tmacc": b}
    playlist = Playlist(items=[PlaylistItem("a.tmacc"), PlaylistItem("b.tmacc")], gap_ms=200)

    built = playlist.build(lambda p: lib[p])
    times = [e.timestamp_ns for e in built.sorted_events()]
    # a at 0,100ms then a 200ms gap, then b at 300ms, 350ms.
    assert times == [0, 100_000_000, 300_000_000, 350_000_000]
    assert built.duration_ns == 350_000_000


def test_build_applies_per_item_repeat():
    a = _macro(0, 100)   # duration 100ms
    playlist = Playlist(items=[PlaylistItem("a.tmacc", repeat=3)], gap_ms=100)

    built = playlist.build(lambda p: a)
    times = [e.timestamp_ns for e in built.sorted_events()]
    # three copies, each 100ms long, separated by 100ms gaps:
    # 0,100 | +200 -> 200,300 | +200 -> 400,500
    assert times == [0, 100_000_000, 200_000_000, 300_000_000, 400_000_000, 500_000_000]


def test_build_carries_variant_flag():
    a = _macro(0)
    docked = Playlist(items=[PlaylistItem("a.tmacd")], docked=True).build(lambda p: a)
    classic = Playlist(items=[PlaylistItem("a.tmacc")], docked=False).build(lambda p: a)
    assert docked.docked is True
    assert classic.docked is False


def test_build_empty_raises():
    import pytest

    with pytest.raises(ValueError):
        Playlist().build(lambda p: _macro(0))


def test_editing_operations():
    playlist = Playlist()
    playlist.add("a.tmacc")
    playlist.add("b.tmacc", repeat=2)
    playlist.add("c.tmacc")
    assert [i.display_name for i in playlist.items] == ["a", "b", "c"]

    new_index = playlist.move(2, -1)  # c up one
    assert new_index == 1
    assert [i.display_name for i in playlist.items] == ["a", "c", "b"]

    playlist.set_repeat(0, 5)
    assert playlist.items[0].repeat == 5
    playlist.set_repeat(0, 0)  # clamped to at least 1
    assert playlist.items[0].repeat == 1

    playlist.remove(1)
    assert [i.display_name for i in playlist.items] == ["a", "b"]


def test_save_load_round_trip(tmp_path):
    playlist = Playlist(
        name="My Combo",
        items=[PlaylistItem("a.tmacc", repeat=2), PlaylistItem("b.tmacc")],
        gap_ms=350,
        docked=False,
    )
    path = tmp_path / "combo.tmplist"
    playlist.save(path)
    restored = Playlist.load(path)
    assert restored.name == "My Combo"
    assert restored.gap_ms == 350
    assert [(i.path, i.repeat) for i in restored.items] == [("a.tmacc", 2), ("b.tmacc", 1)]


def test_load_rejects_foreign_file(tmp_path):
    import json
    import pytest

    path = tmp_path / "bad.tmplist"
    path.write_text(json.dumps({"format": "something-else"}), encoding="utf-8")
    with pytest.raises(ValueError):
        Playlist.load(path)
