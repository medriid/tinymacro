from __future__ import annotations

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import FORMAT_VERSION, Macro
from tinymacro.core.player import Player, _colors_close, _parse_hex_color


def test_new_kinds_round_trip():
    events = [
        MacroEvent.run_step(0, "echo hi", mode="shell", timeout_ms=2000, on_missing="skip"),
        MacroEvent.run_step(0, "print(1)", mode="python"),
        MacroEvent.wait_pixel(0, 10, 20, "#3b82f6", tolerance=0.1),
        MacroEvent.wait_window(0, "Notepad"),
        MacroEvent.loop_start(0, 3),
        MacroEvent.if_image(0, "YWJj"),
        MacroEvent.control(0, "endif"),
    ]
    for event in events:
        assert MacroEvent.from_dict(event.to_dict()) == event
        assert event.is_input is False


def test_format_version_four():
    assert FORMAT_VERSION == 4


def test_hex_helpers():
    assert _parse_hex_color("#3b82f6") == (59, 130, 246)
    assert _parse_hex_color("nope") is None
    assert _colors_close((59, 130, 246), (60, 131, 245), 3)
    assert not _colors_close((0, 0, 0), (255, 255, 255), 3)


class _Backend:
    name = "fake"

    def emit(self, event):
        pass

    def close(self):
        pass


def _run(event, *, allow, on_error=None):
    player = Player(_Backend(), allow_code_execution=allow)
    errors: list[str] = []
    player.on_error = lambda exc: errors.append(str(exc))
    player.start(Macro(events=[event]), loop_count=1, blocking=True)
    return errors


def test_run_step_blocked_when_disabled():
    errors = _run(MacroEvent.run_step(0, "echo x", on_missing="fail"), allow=False)
    assert any("disabled" in e.lower() for e in errors)


def test_run_step_blocked_disabled_but_skip_is_silent():
    errors = _run(MacroEvent.run_step(0, "echo x", on_missing="skip"), allow=False)
    assert errors == []


def test_run_shell_executes_when_enabled():
    # A harmless command that always succeeds.
    errors = _run(MacroEvent.run_step(0, "cd .", mode="shell", on_missing="fail"), allow=True)
    assert errors == []


def test_run_python_executes_when_enabled():
    errors = _run(MacroEvent.run_step(0, "x = 1 + 1", mode="python", on_missing="fail"), allow=True)
    assert errors == []


def test_macro_with_new_steps_serializes():
    macro = Macro(events=[
        MacroEvent(0, "key", "press", key="a"),
        MacroEvent.wait_window(0, "Editor"),
    ])
    restored = Macro.from_dict(macro.to_dict())
    assert any(e.kind == "window" for e in restored.events)
