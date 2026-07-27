"""Fresh-loop behaviour: a settling gap between loops and held-input release.

Uses a virtual clock (the sleeper advances it) so timing is deterministic.
"""
from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


class _Backend:
    name = "fake"

    def __init__(self, clock=None):
        self._clock = clock
        self.emits: list[tuple[str, str, str | None]] = []

    def emit(self, event):
        self.emits.append((event.kind, event.action, event.key or event.button))

    def close(self):
        pass


def test_loop_gap_is_inserted_between_loops_only():
    clock = [0]
    backend = _Backend(clock)
    completions: list[int] = []
    player = Player(
        backend,
        clock_ns=lambda: clock[0],
        sleeper=lambda s: clock.__setitem__(0, clock[0] + int(s * 1e9)),
        loop_gap_ns=50_000_000,
        on_loop_complete=lambda d, t, s, m, shot: completions.append(clock[0]),
    )
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent.wait(0, 200_000_000, note="idle"),
    ])  # 200ms period
    player.start(macro, loop_count=2, speed=1.0, blocking=True)
    # Loop 1 completes at 200ms; a 50ms gap precedes loop 2, which then completes
    # 200ms later — the gap sits *between* loops, never before the first.
    assert completions == [200_000_000, 450_000_000]


def test_held_key_is_released_between_loops_and_at_end():
    backend = _Backend()
    player = Player(backend, sleeper=lambda s: None, reset_between_loops=True)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    # A press with no matching release: the player must not let 'a' bleed across.
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])
    player.start(macro, loop_count=2, speed=1.0, blocking=True)
    assert backend.emits == [
        ("key", "press", "a"),
        ("key", "release", "a"),  # end of loop 1
        ("key", "press", "a"),
        ("key", "release", "a"),  # end of loop 2
    ]


def test_no_spurious_release_when_input_is_balanced():
    backend = _Backend()
    player = Player(backend, sleeper=lambda s: None, reset_between_loops=True)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "release", key="a"),
    ])
    player.start(macro, loop_count=2, speed=1.0, blocking=True)
    # Balanced press/release leaves nothing held, so no cleanup releases are added.
    assert backend.emits == [
        ("key", "press", "a"),
        ("key", "release", "a"),
        ("key", "press", "a"),
        ("key", "release", "a"),
    ]
