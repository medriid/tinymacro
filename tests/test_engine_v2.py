from __future__ import annotations

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import HotkeySet
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player, simulate
from tinymacro.core.recorder import Recorder


class FakeClock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now

    def advance(self, ns: int) -> None:
        self.now += ns

    def sleep(self, seconds: float) -> None:
        self.now += max(1, int(seconds * 1_000_000_000))


# -- recorder -------------------------------------------------------------
def test_recorder_pause_ignores_events():
    backend = FakeBackend()
    clock = FakeClock()
    recorder = Recorder(backend, HotkeySet(), clock_ns=clock, skip_final_click=False)
    recorder.start()
    backend.feed(MacroEvent(0, "key", "press", key="a"))
    recorder.pause()
    backend.feed(MacroEvent(0, "key", "press", key="b"))
    recorder.resume()
    backend.feed(MacroEvent(0, "key", "press", key="c"))
    macro = recorder.stop()
    keys = [e.key for e in macro.sorted_events() if e.kind == "key"]
    assert keys == ["a", "c"]


def test_recorder_undo_segment():
    backend = FakeBackend()
    recorder = Recorder(backend, HotkeySet(), clock_ns=lambda: 0, skip_final_click=False)
    recorder.start()
    backend.feed(MacroEvent(0, "key", "press", key="a"))
    recorder.mark_segment()
    backend.feed(MacroEvent(0, "key", "press", key="b"))
    assert recorder.undo_segment() == 1
    macro = recorder.stop()
    assert [e.key for e in macro.sorted_events() if e.kind == "key"] == ["a"]


def test_recorder_move_sampling_thins_events():
    backend = FakeBackend()
    clock = FakeClock()
    recorder = Recorder(
        backend, HotkeySet(), clock_ns=clock, skip_final_click=False, move_min_interval_ns=5_000_000
    )
    recorder.start()
    for _ in range(10):
        backend.feed(MacroEvent(0, "mouse", "move", x=1, y=1))
        clock.advance(1_000_000)
    macro = recorder.stop()
    assert macro.input_event_count() < 10


# -- player ---------------------------------------------------------------
def test_dry_run_emits_nothing():
    backend = FakeBackend()
    clock = FakeClock()
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a"), MacroEvent(10_000_000, "key", "release", key="a")])
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)
    player.start(macro, loop_count=1, speed=1.0, blocking=True, dry_run=True)
    assert backend.emitted == []


def test_wait_events_are_not_emitted():
    backend = FakeBackend()
    clock = FakeClock()
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a"), MacroEvent.wait(0, 1_000_000), MacroEvent(1_000_000, "key", "release", key="a")])
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)
    player.start(macro, loop_count=1, speed=1.0, blocking=True)
    assert [e.action for e in backend.emitted] == ["press", "release"]


def test_emit_index_single_event():
    backend = FakeBackend()
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a"), MacroEvent(10, "key", "release", key="a")])
    player = Player(backend)
    event = player.emit_index(macro, 1)
    assert event.action == "release"
    assert len(backend.emitted) == 1


def test_simulate_reports_warnings():
    good = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    assert simulate(good).ok
    bad = Macro(events=[MacroEvent(0, "key", "press", key=None)])
    report = simulate(bad)
    assert not report.ok
    assert report.warnings
