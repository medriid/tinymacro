from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
import random
import threading
import time
from typing import TYPE_CHECKING

from tinymacro.backends.base import InputBackend
from tinymacro.core.dock import DockRegion, to_absolute
from tinymacro.core.events import DEFAULT_CONFIDENCE, MacroEvent
from tinymacro.core.macro import Macro

if TYPE_CHECKING:
    from tinymacro.core.vision import Locator

# How often to re-scan the screen while waiting for a click-image target.
IMAGE_POLL_S = 0.15

# -- precise-timing tuning ----------------------------------------------------
# Windows' default scheduler granularity is ~15.6ms, so a plain time.sleep of a
# few milliseconds routinely overshoots by 1-15ms — and by a *different* amount
# each time, depending on system load. Replayed at that resolution, dense events
# lose their small inter-event pauses and each loop drifts differently from the
# last (exactly the "deviation as the loops go on" the user saw).
#
# The fix is a two-stage wait: coarse-sleep the bulk of the interval (with the OS
# timer raised to ~1ms via the backend's precise-timing hooks) and then busy-spin
# the final sub-millisecond slice on a high-resolution clock so we land on the
# deadline to within tens of microseconds — consistently, every loop.
_SPIN_NS = 1_500_000  # spin (busy-wait) the last 1.5ms up to the deadline
_MAX_CHUNK_NS = 20_000_000  # cap coarse sleeps at 20ms so pause/stop stay responsive


def precise_sleep(seconds: float) -> None:
    """Sleep ``seconds`` with sub-millisecond accuracy on real hardware.

    Short requests (<= the spin threshold) are satisfied entirely by busy-waiting
    on ``perf_counter_ns``; longer ones fall back to a plain ``time.sleep`` (the
    caller keeps those below the responsiveness cap). This is the default player
    sleeper; tests inject a virtual-clock sleeper instead, so this never runs
    under the deterministic timing tests.
    """
    if seconds <= 0:
        return
    ns = int(seconds * 1_000_000_000)
    if ns > _SPIN_NS:
        time.sleep(seconds)
        return
    end = time.perf_counter_ns() + ns
    while time.perf_counter_ns() < end:
        pass


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


def _match_control(events: list[MacroEvent]):
    """Resolve control-flow brackets with nesting via stacks.

    Returns (if_else, if_end, else_end, endloop_start) index maps. Unmatched
    markers are simply left out; the interpreter treats a missing target as
    end-of-macro so a malformed macro still terminates.
    """
    if_stack: list[int] = []
    loop_stack: list[int] = []
    if_else: dict[int, int] = {}
    if_end: dict[int, int] = {}
    else_end: dict[int, int] = {}
    endloop_start: dict[int, int] = {}
    for i, event in enumerate(events):
        kind = event.kind
        if kind == "if":
            if_stack.append(i)
        elif kind == "else":
            if if_stack:
                if_else[if_stack[-1]] = i
        elif kind == "endif":
            if if_stack:
                start = if_stack.pop()
                if_end[start] = i
                if start in if_else:
                    else_end[if_else[start]] = i
        elif kind == "loop":
            loop_stack.append(i)
        elif kind == "endloop":
            if loop_stack:
                endloop_start[i] = loop_stack.pop()
    return if_else, if_end, else_end, endloop_start


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


def _control_flow_warnings(events: list[MacroEvent]) -> list[str]:
    """Report unbalanced if/else/endif and loop/endloop blocks."""
    warnings: list[str] = []
    if_depth = 0
    loop_depth = 0
    for index, event in enumerate(events):
        kind = event.kind
        if kind == "if":
            if_depth += 1
        elif kind == "endif":
            if if_depth == 0:
                warnings.append(f"event {index}: 'endif' without a matching 'if'")
            else:
                if_depth -= 1
        elif kind == "else":
            if if_depth == 0:
                warnings.append(f"event {index}: 'else' outside any 'if'")
        elif kind == "loop":
            loop_depth += 1
        elif kind == "endloop":
            if loop_depth == 0:
                warnings.append(f"event {index}: 'endloop' without a matching 'loop'")
            else:
                loop_depth -= 1
    if if_depth:
        warnings.append(f"{if_depth} 'if' block(s) missing an 'endif'")
    if loop_depth:
        warnings.append(f"{loop_depth} 'loop' block(s) missing an 'endloop'")
    return warnings


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
    warnings.extend(_control_flow_warnings(events))
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
    sleeper: Callable[[float], None] = precise_sleep
    # Called once per completed loop with (loops_done, loop_count, speed, macro,
    # screenshot). ``screenshot`` is the PNG captured at this loop's screenshot
    # step, or None if the macro has no screenshot step (or capture failed). It is
    # passed by value so the host never races the next loop for it.
    on_loop_complete: Callable[[int, int, float, Macro, bytes | None], None] | None = None
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
    # When set (Studio docked mode), mouse events carrying fx/fy have their
    # absolute x/y recomputed from the current DockRegion right before emitting,
    # so playback follows the docked window wherever it now sits.
    dock_region_provider: Callable[[], "DockRegion | None"] | None = None
    # Captures the screen when a "screenshot" step is reached, so the webhook can
    # send the image from that exact instant. Returns PNG bytes or None.
    screenshot_capturer: Callable[[], bytes | None] | None = None
    # A small idle inserted *between* loops (not before the first, not after the
    # last) so every iteration starts from a clean, settled state and reads as a
    # fresh run rather than one continuous blur. Nanoseconds; 0 disables it.
    loop_gap_ns: int = 0
    # When true, any key/button the macro pressed but never released is released
    # at the end of each loop, so a held input can't bleed into the next loop.
    reset_between_loops: bool = False
    # Called with a step's source index (into ``macro.sorted_events()``) the moment
    # it is about to run — drives the editor's live current-step highlight.
    on_step: Callable[[int], None] | None = None
    # Source indices at which playback auto-pauses (editor breakpoints). When a
    # step in this set is reached, the player pauses itself and calls
    # ``on_breakpoint`` so the host can surface it; the normal resume continues.
    breakpoints: set[int] = field(default_factory=set)
    on_breakpoint: Callable[[int], None] | None = None
    rng: random.Random = field(default_factory=random.Random)

    state: PlaybackState = field(default_factory=PlaybackState)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _pending_screenshot: bytes | None = None  # captured at this loop's screenshot step
    _held_keys: set[str] = field(default_factory=set)
    _held_buttons: set[str] = field(default_factory=set)

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
            self._emit(self._resolve_coords(event))
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
        has_control = any(event.is_control for event in events)
        try:
            self.backend.begin_precise_timing()
        except Exception:  # noqa: BLE001 - timing hint is best-effort
            pass
        try:
            while not self._stop_event.is_set() and (loop_count == 0 or loops_done < loop_count):
                # A settling gap between iterations, so each loop feels fresh. Not
                # applied before the first loop nor after the last.
                if loops_done and self.loop_gap_ns and not dry_run:
                    self._sleep_until(self.clock_ns() + self.loop_gap_ns)
                    if self._stop_event.is_set():
                        break
                self.state.loop_index = loops_done + 1
                self._pending_screenshot = None  # fresh per loop
                self._held_keys.clear()
                self._held_buttons.clear()

                if has_control:
                    self._execute_controlled(events, speed, dry_run, locator, total)
                else:
                    self._execute_scheduled(events, speed, dry_run, locator, total, duration_ns)

                # Release anything the macro left held so the next loop starts clean.
                if self.reset_between_loops and not dry_run and not self._stop_event.is_set():
                    self._release_held()

                loops_done += 1
                if not self._stop_event.is_set() and self.on_loop_complete:
                    self.on_loop_complete(loops_done, loop_count, speed, macro, self._pending_screenshot)
        except Exception as exc:
            if self.on_error:
                self.on_error(exc)
            else:
                raise
        finally:
            if self.reset_between_loops and not dry_run:
                # Never leave a synthetic key/button stuck down when playback ends.
                self._release_held()
            if locator is not None:
                locator.close()
            try:
                self.backend.end_precise_timing()
            except Exception:  # noqa: BLE001
                pass
            self.state.playing = False
            self.state.paused = False

    def _resolve_coords(self, event: MacroEvent) -> MacroEvent:
        """In docked mode, recompute absolute x/y from the event's fx/fy."""
        if event.fx is None or event.fy is None or self.dock_region_provider is None:
            return event
        region = self.dock_region_provider()
        if region is None or not region.valid:
            return event
        x, y = to_absolute(event.fx, event.fy, region)
        return event._with(x=x, y=y)

    # -- emitting / input-state tracking --------------------------------------
    def _emit(self, event: MacroEvent) -> None:
        """Send one input event and remember any key/button it leaves held."""
        self.backend.emit(event)
        self.state.emitted_events += 1
        if event.kind == "key" and event.key:
            if event.action == "press":
                self._held_keys.add(event.key)
            elif event.action == "release":
                self._held_keys.discard(event.key)
        elif event.kind == "mouse" and event.button and event.action in {"press", "release"}:
            if event.action == "press":
                self._held_buttons.add(event.button)
            else:
                self._held_buttons.discard(event.button)

    def _release_held(self) -> None:
        """Emit releases for every key/button still held from synthetic input."""
        for key in sorted(self._held_keys):
            try:
                self.backend.emit(MacroEvent(0, "key", "release", key=key))
            except Exception:  # noqa: BLE001 - cleanup must never raise
                pass
        for button in sorted(self._held_buttons):
            try:
                self.backend.emit(MacroEvent(0, "mouse", "release", button=button))
            except Exception:  # noqa: BLE001
                pass
        self._held_keys.clear()
        self._held_buttons.clear()

    def _reach_step(self, source_index: int) -> None:
        """Announce a step is about to run, and honour a breakpoint on it.

        Fires ``on_step`` (for the editor's live highlight) then, if this index is
        a breakpoint, pauses the player and fires ``on_breakpoint`` so the host can
        show where it stopped. Blocks here until the host resumes (or stops).
        """
        if self.on_step is not None:
            try:
                self.on_step(source_index)
            except Exception:  # noqa: BLE001 - a UI callback must never break playback
                pass
        if source_index in self.breakpoints and not self._stop_event.is_set():
            self._pause_event.set()
            self.state.paused = True
            if self.on_breakpoint is not None:
                try:
                    self.on_breakpoint(source_index)
                except Exception:  # noqa: BLE001
                    pass
            self._wait_while_paused()

    # -- execution paths ------------------------------------------------------
    def _execute_action(self, event: MacroEvent, locator, dry_run: bool) -> None:
        """Perform a single non-control step (emit / image / automation)."""
        if dry_run:
            return
        if event.is_input:
            self._emit(self._resolve_coords(event))
        elif event.kind == "image":
            self._run_image_event(event, locator)
        elif event.kind in ("run", "pixel", "window"):
            self._run_automation_event(event, locator)
        elif event.kind == "screenshot" and self.screenshot_capturer is not None:
            try:
                self._pending_screenshot = self.screenshot_capturer()
            except Exception:  # noqa: BLE001 - a failed capture must not break playback
                self._pending_screenshot = None

    def _execute_scheduled(self, events, speed, dry_run, locator, total, duration_ns) -> None:
        """Straight-line playback scheduled against absolute timestamps.

        Every event's deadline is measured from a single ``loop_start_ns`` anchor
        captured at the top of *this* loop, so timing never drifts across events
        and each loop replays identically. The final wait to ``duration_ns`` keeps
        recorded trailing idle as part of the loop period.
        """
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
            if not dry_run:
                self._reach_step(index)
                if self._stop_event.is_set():
                    break
            self._execute_action(event, locator, dry_run)
            if self.on_progress:
                self.on_progress(index + 1, total)
            self.state.remaining_ns = max(0, int(duration_ns / speed) - (self.clock_ns() - loop_start_ns))
        next_loop_ns = loop_start_ns + int((duration_ns + drift_ns) / speed)
        self._sleep_until(next_loop_ns)

    def _execute_controlled(self, events, speed, dry_run, locator, total) -> None:
        """Interpret a macro that contains if/else/endif and loop/endloop blocks.

        Loops replay events, so absolute timestamps no longer apply; timing is the
        relative gap between consecutive events. To keep those gaps from drifting
        as the interpreter runs, delays advance a running ``target`` clock rather
        than being measured from "now" each step — so a slightly-late sleep on one
        step doesn't push every later step. The target re-anchors after any jump.
        """
        if_else, if_end, else_end, endloop_start = _match_control(events)
        gaps = [0] + [max(0, events[i].timestamp_ns - events[i - 1].timestamp_ns) for i in range(1, len(events))]
        loop_remaining: dict[int, int | None] = {}
        n = len(events)
        pc = 0
        jumped = True  # first step has no leading delay
        target_ns = self.clock_ns()
        while pc < n and not self._stop_event.is_set():
            self._wait_while_paused()
            if self._stop_event.is_set():
                break
            event = events[pc]
            self.state.current_index = pc

            if jumped:
                # Re-anchor after a branch/loop so timing stays continuous instead
                # of trying to "catch up" across the jump.
                target_ns = self.clock_ns()
                jumped = False
            else:
                if event.kind == "wait":
                    delay = event.duration_ns + (self.rng.randint(0, event.jitter_ns) if event.jitter_ns and not dry_run else 0)
                else:
                    delay = gaps[pc]
                if delay:
                    target_ns += int(delay / speed)
                    self._sleep_until(target_ns)
                if self._stop_event.is_set():
                    break

            kind = event.kind
            if kind == "if":
                taken = True if dry_run else self._eval_condition(event, locator)
                if not taken:
                    pc = if_else.get(pc, if_end.get(pc, n)) + 1
                    jumped = True
                    continue
                pc += 1
                continue
            if kind == "else":
                pc = else_end.get(pc, n) + 1  # true-branch finished → skip to endif
                jumped = True
                continue
            if kind == "endif":
                pc += 1
                continue
            if kind == "loop":
                loop_remaining.setdefault(pc, None if event.count == 0 else event.count)
                pc += 1
                continue
            if kind == "endloop":
                start = endloop_start.get(pc)
                if start is None:
                    pc += 1
                    continue
                remaining = loop_remaining.get(start)
                if remaining is None or remaining > 1:
                    if remaining is not None:
                        loop_remaining[start] = remaining - 1
                    self.sleeper(0.001)  # guard against a hot infinite loop
                    pc = start + 1
                    jumped = True
                    continue
                loop_remaining.pop(start, None)
                pc += 1
                continue

            # A normal action step.
            if not dry_run:
                self._reach_step(pc)
                if self._stop_event.is_set():
                    break
            self._execute_action(event, locator, dry_run)
            if self.on_progress:
                self.on_progress(pc + 1, total)
            pc += 1

    def _eval_condition(self, event: MacroEvent, locator) -> bool:
        """Evaluate an ``if`` condition (currently: is the image on screen?)."""
        try:
            png = base64.b64decode(event.image_b64) if event.image_b64 else b""
        except Exception:  # noqa: BLE001
            png = b""
        if not png or locator is None:
            return False
        return self._search_image(event, locator, png) is not None

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
            self._emit(synthetic)

    def _wait_while_paused(self) -> None:
        while self._pause_event.is_set() and not self._stop_event.is_set():
            self.sleeper(0.02)

    def _sleep_until(self, due_ns: int) -> None:
        """Block until the monotonic clock reaches ``due_ns``.

        Long waits are chunked (capped at ``_MAX_CHUNK_NS``) so a pause or stop is
        noticed promptly; the last slice is handed to the sleeper whole so the
        precise sleeper can spin it out and land on the deadline exactly. Because
        every deadline is absolute, an overshoot on one hop is corrected on the
        next instead of accumulating.
        """
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                self._wait_while_paused()
                continue
            remaining_ns = due_ns - self.clock_ns()
            if remaining_ns <= 0:
                return
            if remaining_ns > _SPIN_NS:
                self.sleeper(min(remaining_ns - _SPIN_NS, _MAX_CHUNK_NS) / 1_000_000_000)
            else:
                self.sleeper(remaining_ns / 1_000_000_000)
                return
