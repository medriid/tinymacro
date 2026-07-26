from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import HotkeySet
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player
from tinymacro.core.recorder import Recorder


class _Backend:
    name = "fake"

    def __init__(self):
        self.cb = None
        self.emitted = []

    def pointer_position(self):
        return (0, 0)

    def start_capture(self, cb):
        self.cb = cb

    def stop_capture(self):
        pass

    def emit(self, event):
        self.emitted.append(event.kind)

    def close(self):
        pass


def test_screenshot_hotkey_default_and_roundtrip():
    keys = HotkeySet()
    assert str(keys.screenshot)
    assert keys.screenshot in keys.control_hotkeys()
    assert HotkeySet.from_dict(keys.to_dict()).screenshot.keys == keys.screenshot.keys


def test_recorder_marks_screenshot_point():
    clock = [0]
    backend = _Backend()
    rec = Recorder(backend, clock_ns=lambda: clock[0], skip_final_click=False)
    rec.start()
    clock[0] = 500_000_000
    rec.add_screenshot_point()
    macro = rec.stop()
    assert any(e.kind == "screenshot" for e in macro.events)


def test_player_captures_at_screenshot_step():
    captured = {"n": 0}

    def capturer():
        captured["n"] += 1
        return b"PNGDATA"

    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent.screenshot(1_000_000),
        MacroEvent(2_000_000, "key", "release", key="a"),
    ])
    player = Player(_Backend(), sleeper=lambda s: None, screenshot_capturer=capturer)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)
    assert captured["n"] == 1
    assert player.consume_marked_screenshot() == b"PNGDATA"
    # consumed → cleared
    assert player.consume_marked_screenshot() is None


def test_player_screenshot_resets_each_loop():
    shots = iter([b"one", b"two"])

    def capturer():
        return next(shots)

    macro = Macro(events=[MacroEvent.screenshot(0), MacroEvent(1_000_000, "key", "press", key="a")])
    seen = []
    player = Player(
        _Backend(), sleeper=lambda s: None, screenshot_capturer=capturer,
        on_loop_complete=lambda d, t, s, m: seen.append(player.consume_marked_screenshot()),
    )
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=2, blocking=True)
    assert seen == [b"one", b"two"]
