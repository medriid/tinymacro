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


def test_recorder_filters_control_keys_and_skips_final_click():
    backend = FakeBackend()
    clock = FakeClock()
    recorder = Recorder(backend, HotkeySet(), clock_ns=clock, skip_final_click=True)

    recorder.start()
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "key", "press", key="ctrl"))
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "key", "press", key="a"))
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "mouse", "press", button="left", x=5, y=5))
    clock.advance(1_000)
    backend.feed(MacroEvent(0, "mouse", "release", button="left", x=5, y=5))

    macro = recorder.stop()

    assert len(macro.events) == 1
    assert macro.events[0].key == "a"
    assert macro.events[0].timestamp_ns == 0


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
