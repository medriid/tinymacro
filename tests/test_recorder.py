from __future__ import annotations

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import HotkeySet
from tinymacro.core.recorder import Recorder


class FakeClock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now

    def advance(self, ns: int) -> None:
        self.now += ns


def test_recorder_filters_only_full_hotkey_chord_and_skips_final_click():
    backend = FakeBackend()
    clock = FakeClock()
    recorder = Recorder(backend, HotkeySet(), clock_ns=clock, skip_final_click=True)

    recorder.start()
    clock.advance(1_000)
    # A lone modifier is legitimate input (e.g. Ctrl+C in the target app), so it
    # is recorded — only the complete global-hotkey chord is swallowed.
    backend.feed(MacroEvent(0, "key", "press", key="a"))
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "mouse", "press", button="left", x=5, y=5))
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "mouse", "release", button="left", x=5, y=5))

    macro = recorder.stop()

    input_events = [event for event in macro.events if event.is_input]
    assert len(input_events) == 1
    assert input_events[0].key == "a"
    assert input_events[0].timestamp_ns == 1_000


def test_recorder_filters_the_full_control_chord_but_records_plain_letters():
    backend = FakeBackend()
    clock = FakeClock()
    recorder = Recorder(backend, HotkeySet(), clock_ns=clock, skip_final_click=False)
    recorder.start()
    # Plain 'r' (a letter used in the record hotkey) must still record.
    backend.feed(MacroEvent(0, "key", "press", key="r"))
    backend.feed(MacroEvent(0, "key", "release", key="r"))
    # The full record chord Ctrl+Shift+Alt+R is swallowed (only the trigger 'r').
    for mod in ("ctrl", "shift", "alt", "r"):
        backend.feed(MacroEvent(0, "key", "press", key=mod))
    for mod in ("r", "alt", "shift", "ctrl"):
        backend.feed(MacroEvent(0, "key", "release", key=mod))
    macro = recorder.stop()
    recorded = [(e.action, e.key) for e in macro.sorted_events() if e.kind == "key"]
    # plain r press/release recorded; the chord's modifiers are recorded (they
    # aren't a full chord on their own) but the trigger 'r' of the chord is not.
    assert ("press", "r") in recorded
    assert recorded.count(("press", "r")) == 1  # only the plain 'r', not the chord's


def test_recorder_stores_start_position_and_accumulates_relative_mouse_motion():
    backend = FakeBackend()
    backend.pointer_position_value = (100, 200)
    clock = FakeClock()
    recorder = Recorder(backend, HotkeySet(), clock_ns=clock, skip_final_click=False)

    recorder.start()
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "mouse", "move", dx=5, dy=-3))
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "mouse", "press", button="left"))

    macro = recorder.stop()

    assert recorder.pointer_anchor_recorded
    assert macro.events[0] == MacroEvent(0, "mouse", "move", x=100, y=200)
    assert macro.events[1].x == 105
    assert macro.events[1].y == 197
    assert macro.events[1].dx == 5
    assert macro.events[1].dy == -3
    assert macro.events[2].button == "left"
    assert macro.events[2].x == 105
    assert macro.events[2].y == 197


def test_recorder_preserves_leading_and_trailing_idle():
    backend = FakeBackend()
    clock = FakeClock()
    recorder = Recorder(backend, HotkeySet(), clock_ns=clock, skip_final_click=False)

    recorder.start()
    clock.advance(2_000_000_000)
    backend.feed(MacroEvent(0, "key", "press", key="a"))
    clock.advance(3_000_000_000)
    macro = recorder.stop()

    events = macro.sorted_events()
    assert events[0] == MacroEvent.wait(
        0, 2_000_000_000, note="recorded idle before first action"
    )
    assert events[1].key == "a"
    assert events[1].timestamp_ns == 2_000_000_000
    assert events[2] == MacroEvent.wait(
        2_000_000_000, 3_000_000_000, note="recorded idle after last action"
    )
    assert macro.duration_ns == 5_000_000_000
