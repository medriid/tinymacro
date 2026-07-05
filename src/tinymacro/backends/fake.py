from __future__ import annotations

from tinymacro.backends.base import BackendCapabilities, EventCallback, HotkeyCallback, InputBackend
from tinymacro.core.events import MacroEvent


class FakeBackend(InputBackend):
    name = "fake"
    capabilities = BackendCapabilities(capture=True, playback=True, global_hotkeys=True)

    def __init__(self) -> None:
        self.capture_callback: EventCallback | None = None
        self.hotkey_callback: HotkeyCallback | None = None
        self.emitted: list[MacroEvent] = []

    def start_capture(self, callback: EventCallback) -> None:
        self.capture_callback = callback

    def stop_capture(self) -> None:
        self.capture_callback = None

    def emit(self, event: MacroEvent) -> None:
        self.emitted.append(event)

    def start_hotkeys(self, callback: HotkeyCallback) -> None:
        self.hotkey_callback = callback

    def stop_hotkeys(self) -> None:
        self.hotkey_callback = None

    def feed(self, event: MacroEvent) -> None:
        if self.capture_callback:
            self.capture_callback(event)

    def press_hotkey(self, *keys: str) -> None:
        if self.hotkey_callback:
            self.hotkey_callback(frozenset(key.lower() for key in keys))
