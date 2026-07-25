from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from tinymacro.core.events import MacroEvent

EventCallback = Callable[[MacroEvent], None]
HotkeyCallback = Callable[[frozenset[str]], None]
PointerPosition: TypeAlias = tuple[int, int]


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

    def pointer_position(self) -> PointerPosition | None:
        return None

    def foreground_window_if_external(self) -> int:
        """Handle of the focused window if it belongs to another process, else 0.

        Used to remember the user's target window so keyboard playback can be
        directed there instead of at Tiny Macro. Backends that can't tell return 0.
        """
        return 0

    def focus_window(self, handle: int) -> bool:
        """Best-effort: give keyboard focus to ``handle`` before playback."""
        return False

    def close(self) -> None:
        self.stop_capture()
        self.stop_hotkeys()
