from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from tinymacro.core.macro import Macro


@dataclass(slots=True)
class LoopEvent:
    """Context passed to every notifier when a playback loop completes."""

    loop_index: int
    total_loops: int
    speed: float
    macro: Macro
    is_final: bool
    screenshot_png: bytes | None = None


class Notifier(ABC):
    """A single delivery channel. Implementations must be thread-safe to call."""

    name = "notifier"

    @abstractmethod
    def enabled_for(self, event: LoopEvent) -> bool:
        raise NotImplementedError

    @abstractmethod
    def send(self, event: LoopEvent) -> None:
        raise NotImplementedError


class NotificationDispatcher:
    """Fans a LoopEvent out to every registered notifier, isolating failures."""

    def __init__(self, on_error: Callable[[str, Exception], None] | None = None) -> None:
        self._notifiers: list[Notifier] = []
        self._on_error = on_error

    def register(self, notifier: Notifier) -> None:
        self._notifiers.append(notifier)

    def clear(self) -> None:
        self._notifiers.clear()

    def dispatch(self, event: LoopEvent) -> list[str]:
        """Send to all channels that want this event. Returns names that fired."""
        fired: list[str] = []
        for notifier in self._notifiers:
            try:
                if notifier.enabled_for(event):
                    notifier.send(event)
                    fired.append(notifier.name)
            except Exception as exc:  # a broken channel must not stop the others
                if self._on_error:
                    self._on_error(notifier.name, exc)
        return fired
