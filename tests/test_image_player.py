from __future__ import annotations

from dataclasses import dataclass

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


@dataclass
class _FakeMatch:
    x: int
    y: int
    score: float = 0.99


class _FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self.emitted: list[tuple] = []

    def emit(self, event) -> None:
        self.emitted.append((event.kind, event.action, event.button, event.x, event.y))

    def close(self) -> None:
        pass


class _FakeLocator:
    def __init__(self, match) -> None:
        self.match = match
        self.calls = 0
        self.closed = False

    def locate(self, png, confidence, region=None, grayscale=True):
        self.calls += 1
        return self.match

    def close(self) -> None:
        self.closed = True


def _play(backend, locator, event, **start):
    player = Player(backend, locator_factory=lambda: locator)
    errors: list[str] = []
    player.on_error = lambda exc: errors.append(str(exc))
    player.start(Macro(events=[event]), loop_count=1, blocking=True, **start)
    return errors


def test_image_found_emits_click_at_offset():
    backend = _FakeBackend()
    locator = _FakeLocator(_FakeMatch(100, 200))
    event = MacroEvent.image_click(0, "YWJj", click_button="left", offset_x=5, offset_y=-5)
    errors = _play(backend, locator, event)
    assert errors == []
    assert backend.emitted == [
        ("mouse", "move", None, 105, 195),
        ("mouse", "press", "left", 105, 195),
        ("mouse", "release", "left", 105, 195),
    ]
    assert locator.closed is True


def test_image_missing_fail_raises():
    backend = _FakeBackend()
    locator = _FakeLocator(None)
    event = MacroEvent.image_click(0, "YWJj", timeout_ms=30, on_missing="fail")
    errors = _play(backend, locator, event)
    assert backend.emitted == []
    assert any("not found" in e.lower() for e in errors)


def test_image_missing_skip_continues():
    backend = _FakeBackend()
    locator = _FakeLocator(None)
    event = MacroEvent.image_click(0, "YWJj", timeout_ms=30, on_missing="skip")
    errors = _play(backend, locator, event)
    assert backend.emitted == []
    assert errors == []


def test_image_found_no_click_when_button_none():
    backend = _FakeBackend()
    locator = _FakeLocator(_FakeMatch(10, 10))
    event = MacroEvent.image_click(0, "YWJj", click_button="none")
    errors = _play(backend, locator, event)
    assert backend.emitted == []
    assert errors == []


def test_dry_run_skips_locator():
    backend = _FakeBackend()
    locator = _FakeLocator(_FakeMatch(1, 1))
    event = MacroEvent.image_click(0, "YWJj")
    _play(backend, locator, event, dry_run=True)
    assert locator.calls == 0
    assert backend.emitted == []
