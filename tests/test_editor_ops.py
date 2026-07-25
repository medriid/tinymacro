from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro


def _macro():
    return Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "press", key="b"),
        MacroEvent(2_000_000, "key", "press", key="c"),
    ])


def test_insert_event_places_before_index():
    macro = _macro()
    result = macro.insert_event(1, MacroEvent(0, "mouse", "press", button="left", x=5, y=5))
    kinds = [(e.kind, e.key or e.button) for e in result.sorted_events()]
    assert kinds == [("key", "a"), ("mouse", "left"), ("key", "b"), ("key", "c")]


def test_insert_event_at_end():
    macro = _macro()
    result = macro.insert_event(99, MacroEvent(0, "wheel", "scroll", dx=0, dy=1))
    assert result.sorted_events()[-1].kind == "wheel"


def test_duplicate_indices():
    result = _macro().duplicate_indices({0, 2})
    assert [e.key for e in result.sorted_events()] == ["a", "a", "b", "c", "c"]


def test_move_index_down_and_up():
    macro = _macro()
    down = macro.move_index(0, 1)
    assert [e.key for e in down.sorted_events()] == ["b", "a", "c"]
    up = down.move_index(1, -1)
    assert [e.key for e in up.sorted_events()] == ["a", "b", "c"]


def test_move_index_at_edges_is_noop():
    macro = _macro()
    assert [e.key for e in macro.move_index(0, -1).sorted_events()] == ["a", "b", "c"]
    assert [e.key for e in macro.move_index(2, 1).sorted_events()] == ["a", "b", "c"]


def test_duplicate_empty_selection_noop():
    macro = _macro()
    assert len(macro.duplicate_indices(set()).events) == 3
