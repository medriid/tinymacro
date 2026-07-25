from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
import random
import threading
import time
from typing import TYPE_CHECKING

from tinymacro.backends.base import InputBackend
from tinymacro.core.events import DEFAULT_CONFIDENCE, MacroEvent
from tinymacro.core.macro import Macro

if TYPE_CHECKING:
    from tinymacro.core.vision import Locator

# How often to re-scan the screen while waiting for a click-image target.
IMAGE_POLL_S = 0.15


@dataclass(slots=True)
class PlaybackState:
    playing: bool = False
    paused: bool = False
    loop_index: int = 0
    emitted_events: int = 0
    remaining_ns: int = 0
    current_index: int = 0


@dataclass(slots=True)
class SimulationReport:
    """Result of validating a macro without sending any real input."""

    ok: bool
    event_count: int
    input_event_count: int
    wait_event_count: int
    duration_ns: int
    warnings: list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return self.duration_ns / 1_000_000_000


def _parse_hex_color(text: str) -> tuple[int, int, int] | None:
    value = text.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


def _colors_close(a: tuple[int, int, int], b: tuple[int, int, int], tolerance: int) -> bool:
    return all(abs(int(x) - int(y)) <= tolerance for x, y in zip(a, b))


def _vision_available() -> bool:
    """True when the optional image-matching deps are importable."""
    try:
        from tinymacro.core.vision import VISION_AVAILABLE

        return VISION_AVAILABLE
    except Exception:  # noqa: BLE001
        return False


def simulate(macro: Macro) -> SimulationReport:
    """Dry-run a macro: check structural sanity and report, emitting nothing."""
    events = macro.sorted_events()
    warnings: list[str] = []
    last_ns = -1
    for index, event in enumerate(events):
        if event.timestamp_ns < 0:
            warnings.append(f"event {index} has negative timestamp")
        if event.timestamp_ns < last_ns:
            warnings.append(f"event {index} is out of order")
        last_ns = event.timestamp_ns
        if event.kind == "mouse" and event.action in {"press", "release"} and event.button is None:
            warnings.append(f"event {index} is a mouse click with no button")
        if event.kind == "key" and event.action in {"press", "release"} and not event.key:
            warnings.append(f"event {index} is a key event with no key")
        if event.kind == "wheel" and not event.dx and not event.dy:
            warnings.append(f"event {index} is a wheel scroll with no delta")
        if event.kind == "mouse" and event.action == "move" and event.x is None and not event.dx and not event.dy:
            warnings.append(f"event {index} is a mouse move with no target")
        if event.kind == "image":
            if not event.image_b64:
                warnings.append(f"event {index} is a click-image step with no image")
            if not (0.0 < event.confidence <= 1.0):
                warnings.append(f"event {index} has an out-of-range confidence")
            if not _vision_available():
                warnings.append(
                    f"event {index} is a click-image step but the 'vision' extras are not installed"
                )
    return SimulationReport(
        ok=not warnings,
        event_count=len(events),
        input_event_count=macro.input_event_count(),
        wait_event_count=macro.wait_event_count(),
        duration_ns=macro.duration_ns,
        warnings=warnings,
    )


@dataclass(slots=True)
class Player:
    backend: InputBackend
    clock_ns: Callable[[], int] = time.monotonic_ns
    sleeper: Callable[[float], None] = time.sleep
    on_loop_complete: Callable[[int, int, float, Macro], None] | None = None
    on_error: Callable[[Exception], None] | None = None
    on_progress: Callable[[int, int], None] | None = None
    # Builds a screen Locator for click-image steps. Called on the playback
    # thread (mss is not thread-safe), once per run, and closed at the end. When
    # None (or vision deps missing) image steps fall back to their on_missing rule.
    locator_factory: Callable[[], "Locator"] | None = None
    # Called (on the playback thread) when a click-image step fails to find its
    # target, so the host can log it and save a failure screenshot for debugging.
    on_image_missed: Callable[[MacroEvent], None] | None = None
    # Gate for ``run`` steps (shell/Python). Off unless the host opts in.
    allow_code_execution: bool = False
    rng: random.Random = field(default_factory=random.Random)

    state: PlaybackState = field(default_factory=PlaybackState)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------------
    def start(
        self,
        macro: Macro,
        loop_count: int = 1,
        speed: float = 1.0,
        blocking: bool = False,
        dry_run: bool = False,
    ) -> None:
        if speed <= 0:
            raise ValueError("Speed must be positive")
        if loop_count < 0:
            raise ValueError("Loop count must be zero or positive")
        self.stop(wait=True)
        self._stop_event.clear()
        self._pause_event.clear()
        self.state = PlaybackState(playing=True)
        target = lambda: self._run(macro, loop_count, speed, dry_run)
        if blocking:
            target()
            return
        self._thread = threading.Thread(target=target, name="tiny-macro-player", daemon=True)
        self._thread.start()

    def stop(self, wait: bool = False) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.state.playing = False
        self.state.paused = False

    def pause(self) -> None:
        if self.state.playing:
            self._pause_event.set()
            self.state.paused = True

    def resume(self) -> None:
        self._pause_event.clear()
        self.state.paused = False

    # -- step / single-shot ---------------------------------------------------
    def emit_index(self, macro: Macro, index: int) -> MacroEvent:
        """Emit a single event by index (used by step-through debugging)."""
        events = macro.sorted_events()
        if not 0 <= index < len(events):
            raise IndexError("Event index out of range")
        event = events[index]
        if event.is_input:
            self.backend.emit(event)
            self.state.emitted_events += 1
        self.state.current_index = index
        return event

    # -- main loop ------------------------------------------------------------
    def _run(self, macro: Macro, loop_count: int, speed: float, dry_run: bool) -> None:
        events = macro.sorted_events()
        if not events:
            self.state.playing = False
            return
        duration_ns = max(1, macro.duration_ns)
        loops_done = 0
        total = len(events)
        locator = self._make_locator(events, dry_run)
        try:
            while not self._stop_event.is_set() and (loop_count == 0 or loops_done < loop_count):
                self.state.loop_index = loops_done + 1
                loop_start_ns = self.clock_ns()
                drift_ns = 0  # accumulated random wait jitter within this loop
                for index, event in enumerate(events):
                    if self._stop_event.is_set():
                        break
                    self._wait_while_paused()
                    if self._stop_event.is_set():
                        break
                    self.state.current_index = index
                    if event.kind == "wait" and event.jitter_ns and not dry_run:
                        drift_ns += self.rng.randint(0, event.jitter_ns)
                    due_ns = loop_start_ns + int((event.timestamp_ns + drift_ns) / speed)
                    self._sleep_until(due_ns)
                    if self._stop_event.is_set():
                        break
                    if event.is_input and not dry_run:
                        self.backend.emit(event)
                        self.state.emitted_events += 1
                    elif event.kind == "image" and not dry_run:
                        self._run_image_event(event, locator)
                    elif event.kind in ("run", "pixel", "window") and not dry_run:
                        self._run_automation_event(event, locator)
                    if self.on_progress:
                        self.on_progress(index + 1, total)
                    self.state.remaining_ns = max(0, int(duration_ns / speed) - (self.clock_ns() - loop_start_ns))
                loops_done += 1
                next_loop_ns = loop_start_ns + int((duration_ns + drift_ns) / speed)
                self._sleep_until(next_loop_ns)
                if not self._stop_event.is_set() and self.on_loop_complete:
                    self.on_loop_complete(loops_done, loop_count, speed, macro)
        except Exception as exc:
            if self.on_error:
                self.on_error(exc)
            else:
                raise
        finally:
            if locator is not None:
                locator.close()
            self.state.playing = False
            self.state.paused = False

    # -- click-image steps ----------------------------------------------------
    def _make_locator(self, events: list[MacroEvent], dry_run: bool):
        """Create one Locator for this run if it needs the screen and deps allow."""
        if dry_run or self.locator_factory is None:
            return None
        if not any(event.kind in ("image", "pixel", "if") for event in events):
            return None
        try:
            return self.locator_factory()
        except Exception:  # noqa: BLE001 - vision unavailable → degrade gracefully
            return None

    def _run_image_event(self, event: MacroEvent, locator) -> None:
        try:
            png = base64.b64decode(event.image_b64) if event.image_b64 else b""
        except Exception:  # noqa: BLE001 - corrupt data is treated as "not found"
            png = b""
        match = self._search_image(event, locator, png) if (png and locator is not None) else None
        if match is not None:
            if event.click_button and event.click_button != "none":
                self._emit_click(match.x + event.offset_x, match.y + event.offset_y, event.click_button)
            return
        # Not found (or unable to search): let the host record the failure, then
        # honor the on_missing policy.
        if self.on_image_missed is not None:
            try:
                self.on_image_missed(event)
            except Exception:  # noqa: BLE001 - diagnostics must never break playback
                pass
        if event.on_missing == "fail":
            raise RuntimeError(f"Image not found within {event.timeout_ms} ms")
        # "skip" / "continue": fall through and keep playing.

    # -- run / pixel / window steps -------------------------------------------
    def _run_automation_event(self, event: MacroEvent, locator) -> None:
        if event.kind == "run":
            self._run_command(event)
            return
        satisfied = self._wait_condition(event, locator)
        if not satisfied and event.on_missing == "fail":
            raise RuntimeError(f"Condition not met within {event.timeout_ms} ms: {event.describe()}")

    def _run_command(self, event: MacroEvent) -> None:
        if not self.allow_code_execution:
            if event.on_missing == "fail":
                raise RuntimeError("Code-execution steps are disabled in Preferences")
            return
        timeout_s = max(0.1, event.timeout_ms / 1000) if event.timeout_ms else None
        try:
            if event.action == "python":
                exec(compile(event.command, "<macro>", "exec"), {"__builtins__": __builtins__})  # noqa: S102
            else:
                import subprocess

                result = subprocess.run(event.command, shell=True, timeout=timeout_s)  # noqa: S602
                if result.returncode != 0 and event.on_missing == "fail":
                    raise RuntimeError(f"Command exited with {result.returncode}")
        except Exception:
            if event.on_missing == "fail":
                raise
            # skip/continue: swallow the failure and keep playing.

    def _wait_condition(self, event: MacroEvent, locator) -> bool:
        if event.kind == "pixel":
            target = _parse_hex_color(event.command)
            tolerance = int(max(0.0, event.confidence) * 255) or 12
            if target is None or locator is None:
                return False

            def check() -> bool:
                rgb = locator.pixel_rgb(event.x or 0, event.y or 0)
                return rgb is not None and _colors_close(rgb, target, tolerance)

            return self._wait_until(check, event.timeout_ms)
        if event.kind == "window":
            from tinymacro.core.window_info import active_window_title

            needle = event.command.lower()

            def check() -> bool:
                title = active_window_title()
                return title is not None and needle in title.lower()

            return self._wait_until(check, event.timeout_ms)
        return False

    def _wait_until(self, check: Callable[[], bool], timeout_ms: int) -> bool:
        deadline = self.clock_ns() + max(0, timeout_ms) * 1_000_000
        while not self._stop_event.is_set():
            self._wait_while_paused()
            if self._stop_event.is_set():
                return False
            try:
                if check():
                    return True
            except Exception:  # noqa: BLE001
                pass
            if self.clock_ns() >= deadline:
                return False
            self.sleeper(IMAGE_POLL_S)
        return False

    def _search_image(self, event: MacroEvent, locator, png: bytes):
        deadline = self.clock_ns() + max(0, event.timeout_ms) * 1_000_000
        confidence = event.confidence or DEFAULT_CONFIDENCE
        while not self._stop_event.is_set():
            self._wait_while_paused()
            if self._stop_event.is_set():
                return None
            try:
                match = locator.locate(png, confidence, event.region, event.grayscale)
            except Exception:  # noqa: BLE001 - a failed capture is just a miss
                match = None
            if match is not None:
                return match
            if self.clock_ns() >= deadline:
                return None
            self.sleeper(IMAGE_POLL_S)
        return None

    def _emit_click(self, x: int, y: int, button: str) -> None:
        x, y = int(x), int(y)
        for synthetic in (
            MacroEvent(timestamp_ns=0, kind="mouse", action="move", x=x, y=y),
            MacroEvent(timestamp_ns=0, kind="mouse", action="press", button=button, x=x, y=y),
            MacroEvent(timestamp_ns=0, kind="mouse", action="release", button=button, x=x, y=y),
        ):
            self.backend.emit(synthetic)
            self.state.emitted_events += 1

    def _wait_while_paused(self) -> None:
        while self._pause_event.is_set() and not self._stop_event.is_set():
            self.sleeper(0.02)

    def _sleep_until(self, due_ns: int) -> None:
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                self._wait_while_paused()
                continue
            remaining_ns = due_ns - self.clock_ns()
            if remaining_ns <= 0:
                return
            self.sleeper(min(remaining_ns / 1_000_000_000, 0.02))
