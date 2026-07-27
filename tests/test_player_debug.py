"""on_step highlighting hook and breakpoint auto-pause."""
from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


class _Backend:
    name = "fake"

    def __init__(self):
        self.emitted: list[str | None] = []

    def emit(self, event):
        self.emitted.append(event.key)

    def close(self):
        pass


def test_on_step_reports_each_index_in_order():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "press", key="b"),
        MacroEvent(2_000_000, "key", "press", key="c"),
    ])
    steps: list[int] = []
    player = Player(_Backend(), sleeper=lambda s: None, on_step=steps.append)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=2, blocking=True)
    # Three steps per loop, twice, each reported by source index.
    assert steps == [0, 1, 2, 0, 1, 2]


def test_breakpoint_pauses_then_resumes():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1_000_000, "key", "press", key="b"),
        MacroEvent(2_000_000, "key", "press", key="c"),
    ])
    backend = _Backend()
    hits: list[int] = []
    player = Player(backend, sleeper=lambda s: None)
    player.breakpoints = {1}

    def on_break(index: int) -> None:
        hits.append(index)
        assert player.state.paused
        # Only 'a' has been emitted when we stop *before* executing step 1.
        assert backend.emitted == ["a"]
        player.resume()  # let it continue past the breakpoint

    player.on_breakpoint = on_break
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)

    assert hits == [1]
    assert backend.emitted == ["a", "b", "c"]


def test_breakpoint_in_controlled_macro():
    # A macro with a loop block exercises the controlled interpreter path.
    events = [
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent.loop_start(0, 2),
        MacroEvent(0, "key", "press", key="b"),
        MacroEvent.control(0, "endloop"),
    ]
    backend = _Backend()
    hits: list[int] = []
    player = Player(backend, sleeper=lambda s: None)
    player.breakpoints = {2}  # the 'b' press inside the loop
    player.on_breakpoint = lambda i: (hits.append(i), player.resume())
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(Macro(events=events), loop_count=1, blocking=True)
    # The loop body runs twice, so the breakpoint is hit on each iteration.
    assert hits == [2, 2]
    assert backend.emitted == ["a", "b", "b"]
