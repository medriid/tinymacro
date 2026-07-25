from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import FORMAT_VERSION, Macro


def _image_event() -> MacroEvent:
    return MacroEvent.image_click(
        1000,
        "aGVsbG8=",
        confidence=0.9,
        timeout_ms=3000,
        on_missing="skip",
        click_button="right",
        offset_x=5,
        offset_y=-3,
        grayscale=False,
        region=(10, 20, 100, 200),
        note="login",
    )


def test_image_event_round_trip():
    event = _image_event()
    restored = MacroEvent.from_dict(event.to_dict())
    assert restored == event
    assert restored.region == (10, 20, 100, 200)
    assert restored.is_input is False


def test_image_describe():
    assert "click" in _image_event().replace(click_button="left").describe()
    assert "find" in _image_event().replace(click_button="none").describe()


def test_non_image_events_stay_lean():
    key = MacroEvent(0, "key", "press", key="a")
    assert "image_b64" not in key.to_dict()
    assert "confidence" not in key.to_dict()


def test_older_macro_files_load_under_v3():
    assert FORMAT_VERSION == 3
    for version in (1, 2):
        data = {
            "format": "tiny-macro",
            "version": version,
            "events": [{"timestamp_ns": 0, "kind": "key", "action": "press", "key": "a"}],
        }
        assert len(Macro.from_dict(data).events) == 1


def test_insert_image_places_step_without_shifting():
    events = [
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "release", key="a"),
    ]
    macro = Macro(events=events)
    result = macro.insert_image(1, _image_event())
    kinds = [e.kind for e in result.sorted_events()]
    assert kinds == ["key", "image", "key"]
    # later event keeps its original timestamp (image adds no fixed duration)
    assert result.sorted_events()[2].timestamp_ns == 1_000_000
    assert result.image_event_count() == 1


def test_macro_with_image_serializes():
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a"), _image_event()])
    restored = Macro.from_dict(macro.to_dict())
    assert restored.image_event_count() == 1
