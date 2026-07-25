from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player, simulate
from tinymacro.core.vision import Match


class _Backend:
    name = "fake"

    def __init__(self):
        self.out: list[str] = []

    def emit(self, event):
        self.out.append(event.key or event.button or event.kind)

    def close(self):
        pass


class _Locator:
    def __init__(self, found):
        self.found = found

    def locate(self, *a, **k):
        return Match(1, 1, 0.99) if self.found else None

    def close(self):
        pass


def _play(events, found=True):
    backend = _Backend()
    player = Player(backend, locator_factory=lambda: _Locator(found), sleeper=lambda s: None)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(Macro(events=events), loop_count=1, blocking=True)
    return backend.out


def test_loop_repeats_body():
    events = [
        MacroEvent.loop_start(0, 3),
        MacroEvent(1000, "key", "press", key="a"),
        MacroEvent.control(2000, "endloop"),
    ]
    assert _play(events) == ["a", "a", "a"]


def test_if_else_true_and_false():
    events = [
        MacroEvent.if_image(0, "YWJj"),
        MacroEvent(1000, "key", "press", key="t"),
        MacroEvent.control(2000, "else"),
        MacroEvent(3000, "key", "press", key="f"),
        MacroEvent.control(4000, "endif"),
    ]
    assert _play(events, found=True) == ["t"]
    assert _play(events, found=False) == ["f"]


def test_if_without_else_skips_body_when_false():
    events = [
        MacroEvent.if_image(0, "YWJj"),
        MacroEvent(1000, "key", "press", key="x"),
        MacroEvent.control(2000, "endif"),
        MacroEvent(3000, "key", "press", key="after"),
    ]
    assert _play(events, found=False) == ["after"]
    assert _play(events, found=True) == ["x", "after"]


def test_nested_loops():
    events = [
        MacroEvent.loop_start(0, 2),
        MacroEvent.loop_start(1000, 2),
        MacroEvent(2000, "key", "press", key="i"),
        MacroEvent.control(3000, "endloop"),
        MacroEvent.control(4000, "endloop"),
    ]
    assert _play(events) == ["i", "i", "i", "i"]


def test_wrap_in_loop_operation():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1000, "key", "press", key="b"),
        MacroEvent(2000, "key", "press", key="c"),
        MacroEvent(3000, "key", "press", key="d"),
    ])
    wrapped = macro.wrap_in_loop({1, 2}, 3)
    kinds = [e.kind for e in wrapped.sorted_events()]
    assert kinds == ["key", "loop", "key", "key", "endloop", "key"]
    assert _play(wrapped.sorted_events()) == ["a", "b", "c", "b", "c", "b", "c", "d"]


def test_wrap_in_if_operation():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent(1000, "key", "press", key="b"),
    ])
    condition = MacroEvent.if_image(0, "YWJj")
    wrapped = macro.wrap_in_if({1}, condition)
    kinds = [e.kind for e in wrapped.sorted_events()]
    assert kinds == ["key", "if", "key", "endif"]


def test_dry_run_flags_unbalanced_blocks():
    bad = Macro(events=[MacroEvent.control(0, "endif"), MacroEvent.loop_start(1000, 2)])
    report = simulate(bad)
    assert report.ok is False
    joined = " ".join(report.warnings)
    assert "endif" in joined and "loop" in joined


def test_dry_run_ok_for_balanced_blocks():
    good = Macro(events=[
        MacroEvent.loop_start(0, 2),
        MacroEvent(1000, "key", "press", key="a"),
        MacroEvent.control(2000, "endloop"),
    ])
    assert simulate(good).ok is True
