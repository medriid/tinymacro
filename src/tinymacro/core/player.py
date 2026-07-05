from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import threading
import time

from tinymacro.backends.base import InputBackend
from tinymacro.core.macro import Macro


@dataclass(slots=True)
class PlaybackState:
    playing: bool = False
    loop_index: int = 0
    emitted_events: int = 0
    remaining_ns: int = 0


@dataclass(slots=True)
class Player:
    backend: InputBackend
    clock_ns: Callable[[], int] = time.monotonic_ns
    sleeper: Callable[[float], None] = time.sleep

    state: PlaybackState = field(default_factory=PlaybackState)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self, macro: Macro, loop_count: int = 1, speed: float = 1.0, blocking: bool = False) -> None:
        if speed <= 0:
            raise ValueError("Speed must be positive")
        if loop_count < 0:
            raise ValueError("Loop count must be zero or positive")
        self.stop(wait=True)
        self._stop_event.clear()
        self.state = PlaybackState(playing=True)
        target = lambda: self._run(macro.normalized(), loop_count, speed)
        if blocking:
            target()
            return
        self._thread = threading.Thread(target=target, name="tiny-macro-player", daemon=True)
        self._thread.start()

    def stop(self, wait: bool = False) -> None:
        self._stop_event.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.state.playing = False

    def _run(self, macro: Macro, loop_count: int, speed: float) -> None:
        events = macro.sorted_events()
        if not events:
            self.state.playing = False
            return
        duration_ns = max(1, macro.duration_ns)
        loops_done = 0
        try:
            while not self._stop_event.is_set() and (loop_count == 0 or loops_done < loop_count):
                self.state.loop_index = loops_done + 1
                loop_start_ns = self.clock_ns()
                for event in events:
                    if self._stop_event.is_set():
                        break
                    due_ns = loop_start_ns + int(event.timestamp_ns / speed)
                    self._sleep_until(due_ns)
                    if self._stop_event.is_set():
                        break
                    self.backend.emit(event)
                    self.state.emitted_events += 1
                    self.state.remaining_ns = max(0, int(duration_ns / speed) - (self.clock_ns() - loop_start_ns))
                loops_done += 1
                next_loop_ns = loop_start_ns + int(duration_ns / speed)
                self._sleep_until(next_loop_ns)
        finally:
            self.state.playing = False

    def _sleep_until(self, due_ns: int) -> None:
        while not self._stop_event.is_set():
            remaining_ns = due_ns - self.clock_ns()
            if remaining_ns <= 0:
                return
            self.sleeper(min(remaining_ns / 1_000_000_000, 0.02))
