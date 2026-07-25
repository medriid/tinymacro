from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import HotkeySet
from tinymacro.core.macro import Macro
from tinymacro.core.recorder import Recorder
from tinymacro.core.settings import Settings


class _NullBackend:
    name = "fake"

    def pointer_position(self):
        return None

    def start_capture(self, cb):
        self._cb = cb

    def stop_capture(self):
        pass

    def emit(self, event):
        pass

    def close(self):
        pass


def test_recorder_add_marker():
    clock = [0]
    rec = Recorder(_NullBackend(), clock_ns=lambda: clock[0])
    rec.start()
    clock[0] = 500_000_000
    rec.add_marker("checkpoint")
    macro = rec.stop()
    markers = [e for e in macro.events if e.kind == "wait" and e.note == "checkpoint"]
    assert len(markers) == 1


def test_add_marker_ignored_when_not_recording():
    rec = Recorder(_NullBackend())
    rec.add_marker("x")
    assert rec.event_count == 0


def test_trim_leading_idle():
    macro = Macro(events=[
        MacroEvent(0, "mouse", "move", x=0, y=0),        # anchor
        MacroEvent(2_000_000_000, "key", "press", key="a"),  # first real action at 2s
        MacroEvent(2_100_000_000, "key", "release", key="a"),
    ])
    trimmed = macro.trim_leading_idle()
    # the first real action should now sit within max_idle of zero
    events = trimmed.sorted_events()
    assert events[0].timestamp_ns == 0
    assert trimmed.duration_ns < macro.duration_ns


def test_trim_leading_idle_shortens_recorded_wait():
    macro = Macro(events=[
        MacroEvent.wait(0, 2_000_000_000, note="recorded idle before first action"),
        MacroEvent(2_000_000_000, "key", "press", key="a"),
    ])
    trimmed = macro.trim_leading_idle()
    events = trimmed.sorted_events()
    assert events[0].kind == "wait"
    assert events[0].duration_ns == 50_000_000
    assert events[1].timestamp_ns == 50_000_000
    assert trimmed.duration_ns == 50_000_000


def test_trim_trailing_idle_shortens_recorded_wait():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent.wait(0, 2_000_000_000, note="recorded idle after last action"),
    ])
    trimmed = macro.trim_trailing_idle()
    events = trimmed.sorted_events()
    assert events[-1].kind == "wait"
    assert events[-1].duration_ns == 50_000_000
    assert trimmed.duration_ns == 50_000_000


def test_marker_hotkey_round_trip_and_default():
    keys = HotkeySet()
    assert str(keys.marker)  # has a default binding
    restored = HotkeySet.from_dict(keys.to_dict())
    assert restored.marker.keys == keys.marker.keys
    assert keys.marker in keys.control_hotkeys()


def test_settings_countdown_and_trim_round_trip():
    s = Settings()
    s.record_countdown = 3
    s.auto_trim_leading = True
    restored = Settings.from_dict(s.to_dict())
    assert restored.record_countdown == 3
    assert restored.auto_trim_leading is True
