from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import time

from tinymacro.backends.base import InputBackend
from tinymacro.core.dock import DockRegion, to_relative
from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import HotkeySet, normalize_key_name
from tinymacro.core.macro import Macro


@dataclass(slots=True)
class Recorder:
    backend: InputBackend
    hotkeys: HotkeySet = field(default_factory=HotkeySet)
    clock_ns: Callable[[], int] = time.monotonic_ns
    skip_final_click: bool = True
    # Minimum spacing between consecutive recorded mouse-move events. 0 keeps
    # every sample; a larger value thins dense motion to shrink macros.
    move_min_interval_ns: int = 0
    # When set (Studio docked mode), captured absolute pointer coordinates are
    # also stored as fractions of the returned DockRegion so the macro is
    # resolution-independent. None keeps classic absolute-only recording.
    dock_region_provider: Callable[[], "DockRegion | None"] | None = None

    _recording: bool = False
    _paused: bool = False
    _start_ns: int = 0
    _paused_ns: int = 0
    _pause_started_ns: int = 0
    _events: list[MacroEvent] = field(default_factory=list)
    _segment_marks: list[int] = field(default_factory=list)
    _last_move_ns: int = -1
    _pointer_x: int | None = None
    _pointer_y: int | None = None
    pointer_anchor_recorded: bool = False

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def event_count(self) -> int:
        return len(self._events)

    def start(self) -> None:
        if self._recording:
            return
        self._events = []
        self._segment_marks = []
        self._paused = False
        self._paused_ns = 0
        self._last_move_ns = -1
        self._pointer_x = None
        self._pointer_y = None
        self.pointer_anchor_recorded = False
        position = self.backend.pointer_position()
        if position is not None:
            self._pointer_x, self._pointer_y = position
            self.pointer_anchor_recorded = True
            self._events.append(MacroEvent(0, "mouse", "move", x=self._pointer_x, y=self._pointer_y))
        self._start_ns = self.clock_ns()
        self._recording = True
        self.backend.start_capture(self._on_event)

    def pause(self) -> None:
        """Temporarily stop recording new events without ending the session."""
        if not self._recording or self._paused:
            return
        self._paused = True
        self._pause_started_ns = self.clock_ns()

    def resume(self) -> None:
        if not self._recording or not self._paused:
            return
        self._paused_ns += max(0, self.clock_ns() - self._pause_started_ns)
        self._paused = False

    def add_marker(self, note: str = "marker") -> None:
        """Drop a labelled zero-length wait as a bookmark/comment in the timeline."""
        if not self._recording:
            return
        offset = max(0, self.clock_ns() - self._start_ns - self._paused_ns)
        self._events.append(MacroEvent.wait(offset, 0, 0, note=note))

    def mark_segment(self) -> None:
        """Remember the current position so a later ``undo_segment`` can revert."""
        self._segment_marks.append(len(self._events))

    def undo_segment(self) -> int:
        """Drop events recorded since the last segment mark. Returns removed count."""
        if not self._segment_marks:
            return self.undo_last(len(self._events))
        mark = self._segment_marks.pop()
        removed = len(self._events) - mark
        if removed > 0:
            del self._events[mark:]
        return max(0, removed)

    def undo_last(self, count: int = 1) -> int:
        removed = 0
        while count > 0 and self._events:
            self._events.pop()
            removed += 1
            count -= 1
        return removed

    def stop(self) -> Macro:
        if not self._recording:
            return Macro(events=list(self._events), backend=self.backend.name).normalized()
        self.backend.stop_capture()
        self._recording = False
        self._paused = False
        events = list(self._events)
        if self.skip_final_click:
            events = self._drop_final_mouse_press_release(events)
        return Macro(events=events, backend=self.backend.name).normalized()

    def _on_event(self, event: MacroEvent) -> None:
        if self._paused:
            return
        if self._is_control_event(event):
            return
        offset = max(0, self.clock_ns() - self._start_ns - self._paused_ns)
        if event.kind == "mouse" and event.action == "move" and self.move_min_interval_ns > 0:
            if self._last_move_ns >= 0 and offset - self._last_move_ns < self.move_min_interval_ns:
                # Still advance the running pointer estimate so later absolute
                # coordinates stay correct even when we drop the sample.
                self._coordinates_for(event)
                return
            self._last_move_ns = offset
        x, y = self._coordinates_for(event)
        fx = fy = None
        if x is not None and y is not None and self.dock_region_provider is not None:
            region = self.dock_region_provider()
            if region is not None and region.valid:
                fx, fy = to_relative(x, y, region)
        self._events.append(
            MacroEvent(
                timestamp_ns=offset,
                kind=event.kind,
                action=event.action,
                key=event.key,
                button=event.button,
                x=x,
                y=y,
                dx=event.dx,
                dy=event.dy,
                fx=fx,
                fy=fy,
            )
        )

    def _coordinates_for(self, event: MacroEvent) -> tuple[int | None, int | None]:
        if event.kind not in {"mouse", "wheel"}:
            return event.x, event.y
        if event.x is not None and event.y is not None:
            self._pointer_x = event.x
            self._pointer_y = event.y
            return event.x, event.y
        if event.kind == "mouse" and event.action == "move" and (event.dx or event.dy):
            if self._pointer_x is not None and self._pointer_y is not None:
                self._pointer_x += event.dx
                self._pointer_y += event.dy
                return self._pointer_x, self._pointer_y
        if self._pointer_x is not None and self._pointer_y is not None:
            return self._pointer_x, self._pointer_y
        return event.x, event.y

    def _is_control_event(self, event: MacroEvent) -> bool:
        if event.kind != "key" or not event.key:
            return False
        key = normalize_key_name(event.key)
        return any(key in hotkey.keys for hotkey in self.hotkeys.control_hotkeys())

    @staticmethod
    def _drop_final_mouse_press_release(events: list[MacroEvent]) -> list[MacroEvent]:
        result = list(events)
        while result and result[-1].kind == "mouse" and result[-1].action in {"press", "release"}:
            result.pop()
        return result
