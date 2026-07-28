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

    def type_text(self, text: str) -> None:
        """Type ``text`` as unicode keyboard input.

        Backends that can't inject arbitrary unicode raise ``NotImplementedError``;
        the player then skips a text step rather than failing.
        """
        raise NotImplementedError("Backend does not support typing text")

    def start_hotkeys(self, callback: HotkeyCallback) -> None:
        raise NotImplementedError("Backend does not support global hotkeys")

    def stop_hotkeys(self) -> None:
        pass

    def pointer_position(self) -> PointerPosition | None:
        return None

    # -- precise timing (playback) -------------------------------------------
    def begin_precise_timing(self) -> None:
        """Hint the OS to use a high-resolution timer during playback.

        Default is a no-op; the Windows backend raises the system timer
        resolution so short sleeps in the player are accurate to ~1ms.
        """

    def end_precise_timing(self) -> None:
        """Undo :meth:`begin_precise_timing`."""

    def foreground_window_if_external(self) -> int:
        """Handle of the focused window if it belongs to another process, else 0.

        Used to remember the user's target window so keyboard playback can be
        directed there instead of at Tiny Macro. Backends that can't tell return 0.
        """
        return 0

    def focus_window(self, handle: int) -> bool:
        """Best-effort: give keyboard focus to ``handle`` before playback."""
        return False

    # -- window docking (Studio UI); Windows-first, no-op elsewhere -----------
    def supports_docking(self) -> bool:
        """True if this backend can enumerate/move windows for docked mode."""
        return False

    def list_windows(self) -> list[tuple[int, str]]:
        """Return (handle, title) for visible, titled top-level windows."""
        return []

    def window_client_rect(self, handle: int) -> tuple[int, int, int, int] | None:
        """Return the window's client area as (left, top, width, height) in screen px."""
        return None

    def move_resize_window(self, handle: int, left: int, top: int, width: int, height: int) -> bool:
        """Position + size ``handle`` so the whole window fills the given rect."""
        return False

    def close(self) -> None:
        self.stop_capture()
        self.stop_hotkeys()
