"""Shared capture/playback backend built on `pynput`.

`pynput` exposes one API over two very different platform layers — Xorg on Linux
and Quartz/CoreGraphics on macOS — so the X11 and macOS backends differ only in
their ``name``, capability flags, and a couple of platform notes. Everything that
actually records and replays input lives here; :class:`~tinymacro.backends.x11.
X11Backend` and :class:`~tinymacro.backends.macos.MacBackend` are thin subclasses.
"""
from __future__ import annotations

from threading import Lock

from tinymacro.backends.base import BackendCapabilities, EventCallback, HotkeyCallback, InputBackend
from tinymacro.core.events import MacroEvent


def _button_name(button: object) -> str:
    name = getattr(button, "name", None)
    return str(name or button).replace("Button.", "")


def _key_name(key: object) -> str:
    char = getattr(key, "char", None)
    if char:
        return str(char).lower()
    name = getattr(key, "name", None)
    raw = str(name or key).replace("Key.", "").lower()
    aliases = {
        "ctrl_l": "ctrl",
        "ctrl_r": "ctrl",
        "shift_l": "shift",
        "shift_r": "shift",
        "alt_l": "alt",
        "alt_r": "alt",
        # macOS names the Option key "alt" already; Command comes through as one
        # of these. Everything collapses to the canonical "super" so a macro
        # recorded on one platform reads the same on another.
        "cmd": "super",
        "cmd_l": "super",
        "cmd_r": "super",
        "scroll_lock": "scrolllock",
    }
    return aliases.get(raw, raw)


class PynputBackend(InputBackend):
    """Capture + playback + global hotkeys via ``pynput``.

    Subclasses only set :attr:`name` and :attr:`capabilities`; they may override
    :meth:`_ensure_permissions` to fail early with a platform-specific hint.
    """

    name = "pynput"
    capabilities = BackendCapabilities(capture=True, playback=True, global_hotkeys=True)

    def __init__(self) -> None:
        try:
            from pynput import keyboard, mouse
        except Exception as exc:  # pragma: no cover - depends on desktop session
            raise RuntimeError(f"pynput is required for the {self.name} backend") from exc
        self.keyboard = keyboard
        self.mouse = mouse
        self._mouse_listener = None
        self._keyboard_listener = None
        self._hotkey_listener = None
        self._mouse_controller = mouse.Controller()
        self._keyboard_controller = keyboard.Controller()
        self._pressed: set[str] = set()
        self._pressed_lock = Lock()
        self._hotkey_callback: HotkeyCallback | None = None
        self._ensure_permissions()

    def _ensure_permissions(self) -> None:
        """Hook for subclasses to verify OS input permissions up front."""

    def start_capture(self, callback: EventCallback) -> None:
        if self._mouse_listener or self._keyboard_listener:
            return

        def on_move(x: int, y: int) -> None:
            callback(MacroEvent(0, "mouse", "move", x=x, y=y))

        def on_click(x: int, y: int, button: object, pressed: bool) -> None:
            callback(MacroEvent(0, "mouse", "press" if pressed else "release", button=_button_name(button), x=x, y=y))

        def on_scroll(x: int, y: int, dx: int, dy: int) -> None:
            callback(MacroEvent(0, "wheel", "scroll", x=x, y=y, dx=dx, dy=dy))

        def on_press(key: object) -> None:
            callback(MacroEvent(0, "key", "press", key=_key_name(key)))

        def on_release(key: object) -> None:
            callback(MacroEvent(0, "key", "release", key=_key_name(key)))

        self._mouse_listener = self.mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        self._keyboard_listener = self.keyboard.Listener(on_press=on_press, on_release=on_release)
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop_capture(self) -> None:
        for listener_name in ("_mouse_listener", "_keyboard_listener"):
            listener = getattr(self, listener_name)
            if listener:
                listener.stop()
                setattr(self, listener_name, None)

    def pointer_position(self) -> tuple[int, int] | None:
        x, y = self._mouse_controller.position
        return int(x), int(y)

    def emit(self, event: MacroEvent) -> None:
        if event.kind == "mouse":
            if event.x is not None and event.y is not None:
                self._mouse_controller.position = (event.x, event.y)
            if event.action in {"press", "release"} and event.button:
                button = getattr(self.mouse.Button, event.button, self.mouse.Button.left)
                if event.action == "press":
                    self._mouse_controller.press(button)
                else:
                    self._mouse_controller.release(button)
        elif event.kind == "wheel":
            self._mouse_controller.scroll(event.dx, event.dy)
        elif event.kind == "key" and event.key:
            key = self._to_pynput_key(event.key)
            if event.action == "press":
                self._keyboard_controller.press(key)
            elif event.action == "release":
                self._keyboard_controller.release(key)

    def type_text(self, text: str) -> None:
        """Type ``text`` as unicode using pynput's layout-aware typing."""
        self._keyboard_controller.type(text)

    def start_hotkeys(self, callback: HotkeyCallback) -> None:
        if self._hotkey_listener:
            return
        self._hotkey_callback = callback

        def on_press(key: object) -> None:
            name = _key_name(key)
            with self._pressed_lock:
                self._pressed.add(name)
                callback(frozenset(self._pressed))

        def on_release(key: object) -> None:
            name = _key_name(key)
            with self._pressed_lock:
                self._pressed.discard(name)

        self._hotkey_listener = self.keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.start()

    def stop_hotkeys(self) -> None:
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        self._hotkey_callback = None

    def _to_pynput_key(self, key: str) -> object:
        mapped = {"ctrl": "ctrl", "control": "ctrl", "super": "cmd", "scrolllock": "scroll_lock"}
        attr = mapped.get(key.lower(), key.lower())
        if len(attr) == 1:
            return attr
        return getattr(self.keyboard.Key, attr, attr)
