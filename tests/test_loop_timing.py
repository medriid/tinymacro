"""Playback timing: idle is part of the loop period and loops never speed up.

Uses a virtual clock (the sleeper advances the clock) so timing is measured
deterministically without real sleeps.
"""
from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


class _Backend:
    name = "fake"

    def __init__(self, clock):
        self._clock = clock
        self.emits: list[int] = []

    def emit(self, event):
        self.emits.append(self._clock[0])

    def close(self):
        pass


def _play(macro, loops, speed=1.0):
    clock = [0]
    backend = _Backend(clock)
    completions: list[int] = []
    player = Player(
        backend,
        clock_ns=lambda: clock[0],
        sleeper=lambda s: clock.__setitem__(0, clock[0] + int(s * 1e9)),
        on_loop_complete=lambda d, t, s, m: completions.append(clock[0]),
    )
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=loops, speed=speed, blocking=True)
    return backend.emits, completions


def test_duration_includes_trailing_idle():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent.wait(0, 400_000_000, note="trailing idle"),
    ])
    # last real action at 0, plus a 400ms trailing idle wait => 400ms total.
    assert macro.duration_ns == 400_000_000


def test_loops_are_evenly_spaced_and_include_idle():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(100_000_000, "key", "press", key="b"),
        MacroEvent.wait(100_000_000, 400_000_000, note="idle"),
    ])
    assert macro.duration_ns == 500_000_000  # 100ms of action + 400ms idle
    _emits, completions = _play(macro, loops=3)
    # Each loop is exactly 500ms — no speed-up, idle fully counted.
    assert completions == [500_000_000, 1_000_000_000, 1_500_000_000]


def test_inter_event_gaps_are_preserved_every_loop():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(300_000_000, "key", "press", key="b"),
    ])
    emits, _ = _play(macro, loops=2)
    # loop 1: 0, 300ms ; loop 2: 300ms, 600ms (300ms period == last event)
    assert emits == [0, 300_000_000, 300_000_000, 600_000_000]
