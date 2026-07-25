from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player, simulate


def test_dry_run_flags_structural_problems():
    macro = Macro(events=[
        MacroEvent(0, "wheel", "scroll"),  # no delta
        MacroEvent(1000, "image", "click", image_b64="", confidence=1.5),  # empty + bad conf
    ])
    report = simulate(macro)
    assert report.ok is False
    joined = " ".join(report.warnings)
    assert "wheel scroll with no delta" in joined
    assert "no image" in joined
    assert "confidence" in joined


class _Backend:
    name = "fake"

    def emit(self, event):
        pass

    def close(self):
        pass


class _MissLocator:
    def locate(self, *a, **k):
        return None

    def close(self):
        pass


def test_on_image_missed_fires():
    seen = []
    player = Player(
        _Backend(),
        locator_factory=lambda: _MissLocator(),
        on_image_missed=lambda ev: seen.append(ev),
    )
    player.on_error = lambda exc: None
    event = MacroEvent.image_click(0, "YWJj", timeout_ms=20, on_missing="skip")
    player.start(Macro(events=[event]), loop_count=1, blocking=True)
    assert len(seen) == 1
