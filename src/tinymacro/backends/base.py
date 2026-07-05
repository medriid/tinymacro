from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from tinymacro.core.events import MacroEvent

EventCallback = Callable[[MacroEvent], None]
HotkeyCallback = Callable[[frozenset[str]], None]


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    capture: bool
    playback: bool
    global_hotkeys: bool
    requires_privileges: bool = False


class InputBackend(ABC):
    name = "base"
    capabilities = BackendCapabilities(False, False, False)

    @abstractmethod
    def start_capture(self, callback: EventCallback) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop_capture(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def emit(self, event: MacroEvent) -> None:
        raise NotImplementedError

    def start_hotkeys(self, callback: HotkeyCallback) -> None:
        raise NotImplementedError("Backend does not support global hotkeys")

    def stop_hotkeys(self) -> None:
        pass

    def close(self) -> None:
        self.stop_capture()
        self.stop_hotkeys()
