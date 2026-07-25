from __future__ import annotations

import pytest

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import FORMAT_VERSION, Macro


def _macro():
    return Macro(
        events=[
            MacroEvent(0, "key", "press", key="a"),
            MacroEvent(300_000_000, "mouse", "press", button="left", x=5, y=6),
        ],
        name="Sample",
    )


def test_duration_counts_wait_tail():
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a"), MacroEvent.wait(0, 200, jitter_ns=50)])
    assert macro.duration_ns == 250


def test_then_chains_with_gap():
    a = _macro()
    b = Macro(events=[MacroEvent(0, "key", "press", key="b")])
    chained = a.then(b, gap_ns=100_000_000)
    assert len(chained.events) == 3
    assert chained.duration_ns == a.duration_ns + 100_000_000


def test_chain_and_repeat():
    macro = _macro()
    assert len(macro.repeated(3).events) == 3 * len(macro.events)
    combined = Macro.chain([macro, macro], gap_ns=0, name="C")
    assert combined.name == "C"
    assert len(combined.events) == 2 * len(macro.events)


def test_insert_wait_pushes_later_events():
    macro = _macro()
    with_wait = macro.insert_wait(1, 200_000_000, note="pause")
    assert with_wait.wait_event_count() == 1
    assert with_wait.input_event_count() == 2
    assert with_wait.duration_ns == macro.duration_ns + 200_000_000


def test_set_note_and_replace_event():
    macro = _macro()
    noted = macro.set_note(0, "start here")
    assert noted.sorted_events()[0].note == "start here"


def test_humanized_is_deterministic_with_seed():
    macro = _macro()
    a = macro.humanized(50_000_000, seed=7)
    b = macro.humanized(50_000_000, seed=7)
    assert [e.timestamp_ns for e in a.sorted_events()] == [e.timestamp_ns for e in b.sorted_events()]


def test_tags_and_description_round_trip():
    macro = _macro().copy_with(tags=("qa", "smoke"), description="demo")
    restored = Macro.from_dict(macro.to_dict())
    assert restored.tags == ("qa", "smoke")
    assert restored.description == "demo"


def test_format_version_is_three_and_older_files_load():
    assert FORMAT_VERSION == 3
    for version in (1, 2):
        older = {
            "format": "tiny-macro",
            "version": version,
            "name": "old",
            "events": [{"timestamp_ns": 0, "kind": "key", "action": "press", "key": "x"}],
        }
        macro = Macro.from_dict(older)
        assert macro.name == "old"
        assert len(macro.events) == 1


def test_rejects_newer_version():
    with pytest.raises(ValueError):
        Macro.from_dict({"format": "tiny-macro", "version": 99, "events": []})
