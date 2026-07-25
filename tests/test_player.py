from __future__ import annotations

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


class FakeClock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(1, int(seconds * 1_000_000_000))


class FailingBackend(FakeBackend):
    def emit(self, event: MacroEvent) -> None:
        raise RuntimeError("emit failed")


def test_player_uses_absolute_schedule_without_loop_drift():
    backend = FakeBackend()
    clock = FakeClock()
    macro = Macro(
        events=[
            MacroEvent(0, "key", "press", key="a"),
            MacroEvent(100_000_000, "key", "release", key="a"),
        ]
    )
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)

    player.start(macro, loop_count=3, speed=1.0, blocking=True)

    assert [event.key for event in backend.emitted] == ["a", "a", "a", "a", "a", "a"]
    assert clock.now == 300_000_000
    assert not player.state.playing


def test_player_speed_scales_duration():
    backend = FakeBackend()
    clock = FakeClock()
    macro = Macro(events=[MacroEvent(100_000_000, "key", "press", key="a")])
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)

    player.start(macro, loop_count=1, speed=2.0, blocking=True)

    assert clock.now == 50_000_000


def test_player_honors_trailing_recorded_idle():
    backend = FakeBackend()
    clock = FakeClock()
    macro = Macro(
        events=[
            MacroEvent(0, "key", "press", key="a"),
            MacroEvent.wait(0, 300_000_000, note="recorded idle after last action"),
        ]
    )
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)

    player.start(macro, loop_count=2, speed=1.0, blocking=True)

    assert [event.key for event in backend.emitted] == ["a", "a"]
    assert clock.now == 600_000_000


def test_player_calls_loop_complete_after_each_loop():
    backend = FakeBackend()
    clock = FakeClock()
    calls = []
    macro = Macro(events=[MacroEvent(10_000_000, "key", "press", key="a")])
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)
    player.on_loop_complete = lambda loop, total, speed, played: calls.append((loop, total, speed, played.duration_ns))

    player.start(macro, loop_count=2, speed=1.0, blocking=True)

    assert calls == [(1, 2, 1.0, 10_000_000), (2, 2, 1.0, 10_000_000)]


def test_player_reports_emit_errors():
    errors = []
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    player = Player(FailingBackend())
    player.on_error = errors.append

    player.start(macro, blocking=True)

    assert len(errors) == 1
    assert "emit failed" in str(errors[0])
    assert not player.state.playing
