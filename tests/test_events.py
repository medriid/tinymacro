from __future__ import annotations

from tinymacro.core.events import MacroEvent


def test_v1_event_dict_is_unchanged_shape():
    event = MacroEvent(0, "key", "press", key="a")
    data = event.to_dict()
    # No v2-only keys should appear when features are unused.
    assert "duration_ns" not in data
    assert "jitter_ns" not in data
    assert "note" not in data


def test_v2_fields_round_trip():
    event = MacroEvent.wait(1000, 500, jitter_ns=200, note="pause")
    restored = MacroEvent.from_dict(event.to_dict())
    assert restored == event
    assert restored.kind == "wait"
    assert restored.is_input is False


def test_legacy_mouse_button_migration():
    event = MacroEvent.from_dict({"timestamp_ns": 0, "kind": "key", "action": "press", "key": "btn_left"})
    assert event.kind == "mouse"
    assert event.button == "left"


def test_scaled_scales_duration_and_jitter():
    event = MacroEvent.wait(1000, 400, jitter_ns=100)
    scaled = event.scaled(2.0)
    assert scaled.timestamp_ns == 2000
    assert scaled.duration_ns == 800
    assert scaled.jitter_ns == 200


def test_describe_is_human_readable():
    assert "wait" in MacroEvent.wait(0, 500).describe()
    assert "key" in MacroEvent(0, "key", "press", key="a").describe()
