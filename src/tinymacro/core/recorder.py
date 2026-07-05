from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import time

from tinymacro.backends.base import InputBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.hotkeys import HotkeySet, normalize_key_name
from tinymacro.core.macro import Macro


@dataclass(slots=True)
class Recorder:
    backend: InputBackend
    hotkeys: HotkeySet = field(default_factory=HotkeySet)
    clock_ns: Callable[[], int] = time.monotonic_ns
    skip_final_click: bool = True

    _recording: bool = False
    _start_ns: int = 0
    _events: list[MacroEvent] = field(default_factory=list)

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        self._events = []
        self._start_ns = self.clock_ns()
        self._recording = True
        self.backend.start_capture(self._on_event)

    def stop(self) -> Macro:
        if not self._recording:
            return Macro(events=list(self._events), backend=self.backend.name).normalized()
        self.backend.stop_capture()
        self._recording = False
        events = list(self._events)
        if self.skip_final_click:
            events = self._drop_final_mouse_press_release(events)
        return Macro(events=events, backend=self.backend.name).normalized()

    def _on_event(self, event: MacroEvent) -> None:
        if self._is_control_event(event):
            return
        offset = max(0, self.clock_ns() - self._start_ns)
        self._events.append(
            MacroEvent(
                timestamp_ns=offset,
                kind=event.kind,
                action=event.action,
                key=event.key,
                button=event.button,
                x=event.x,
                y=event.y,
                dx=event.dx,
                dy=event.dy,
            )
        )

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
