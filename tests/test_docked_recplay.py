from __future__ import annotations

from tinymacro.core.dock import DockRegion
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player
from tinymacro.core.recorder import Recorder


class _Backend:
    name = "fake"

    def __init__(self):
        self.cb = None
        self.emitted: list[tuple] = []

    def pointer_position(self):
        return (500, 500)

    def start_capture(self, cb):
        self.cb = cb

    def stop_capture(self):
        pass

    def emit(self, event):
        self.emitted.append((event.kind, event.action, event.x, event.y))

    def close(self):
        pass


def test_recorder_stores_relative_coords():
    backend = _Backend()
    region = DockRegion(0, 0, 1000, 1000)
    rec = Recorder(backend, dock_region_provider=lambda: region, skip_final_click=False)
    rec.start()
    backend.cb(MacroEvent(0, "mouse", "press", button="left", x=250, y=750))
    macro = rec.stop()
    click = next(e for e in macro.events if e.action == "press")
    assert click.fx == 0.25 and click.fy == 0.75


def test_player_resolves_relative_to_current_region():
    macro = Macro(events=[MacroEvent(0, "mouse", "press", button="left", x=0, y=0, fx=0.25, fy=0.75)])
    backend = _Backend()
    region = DockRegion(100, 100, 2000, 2000)
    player = Player(backend, dock_region_provider=lambda: region, sleeper=lambda s: None)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)
    assert ("mouse", "press", 600, 1600) in backend.emitted


def test_classic_macro_ignores_absolute_when_no_provider():
    macro = Macro(events=[MacroEvent(0, "mouse", "press", button="left", x=42, y=99)])
    backend = _Backend()
    player = Player(backend, sleeper=lambda s: None)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)
    assert ("mouse", "press", 42, 99) in backend.emitted


def test_fx_fy_serialization_round_trip():
    event = MacroEvent(0, "mouse", "press", button="left", x=1, y=2, fx=0.3, fy=0.6)
    data = event.to_dict()
    assert data["fx"] == 0.3 and data["fy"] == 0.6
    assert MacroEvent.from_dict(data).fx == 0.3
    # A plain event carries no fx/fy keys.
    assert "fx" not in MacroEvent(0, "key", "press", key="a").to_dict()
