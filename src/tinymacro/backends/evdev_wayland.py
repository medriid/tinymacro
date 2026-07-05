from __future__ import annotations

import os
import select
import threading
from pathlib import Path

from tinymacro.backends.base import BackendCapabilities, EventCallback, HotkeyCallback, InputBackend
from tinymacro.core.events import MacroEvent


KEY_ALIASES = {
    "ctrl": "KEY_LEFTCTRL",
    "shift": "KEY_LEFTSHIFT",
    "alt": "KEY_LEFTALT",
    "super": "KEY_LEFTMETA",
    "enter": "KEY_ENTER",
    "return": "KEY_ENTER",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "space": "KEY_SPACE",
    "tab": "KEY_TAB",
    "pause": "KEY_PAUSE",
    "break": "KEY_PAUSE",
    "scrolllock": "KEY_SCROLLLOCK",
}

BUTTON_ALIASES = {
    "left": "BTN_LEFT",
    "right": "BTN_RIGHT",
    "middle": "BTN_MIDDLE",
}

EVDEV_KEY_NAMES = {
    "leftctrl": "ctrl",
    "rightctrl": "ctrl",
    "leftshift": "shift",
    "rightshift": "shift",
    "leftalt": "alt",
    "rightalt": "alt",
    "leftmeta": "super",
    "rightmeta": "super",
    "scrolllock": "scrolllock",
}


class WaylandEvdevBackend(InputBackend):
    """Linux input backend that works below the display server.

    This backend needs read access to /dev/input/event* for capture and write
    access to /dev/uinput for playback. It is suitable for Wayland only when the
    user has configured those permissions.
    """

    name = "wayland-evdev"
    capabilities = BackendCapabilities(capture=True, playback=True, global_hotkeys=True, requires_privileges=True)

    def __init__(self, devices: list[str] | None = None) -> None:
        try:
            from evdev import InputDevice, UInput, ecodes
        except Exception as exc:  # pragma: no cover - depends on Linux packages
            raise RuntimeError("python-evdev is required for the Wayland backend") from exc
        self.InputDevice = InputDevice
        self.UInput = UInput
        self.ecodes = ecodes
        self.device_paths = devices or [str(path) for path in Path("/dev/input").glob("event*")]
        self.devices = []
        self.ui = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._hotkey_callback: HotkeyCallback | None = None
        self._pressed: set[str] = set()

    def start_capture(self, callback: EventCallback) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.devices = [self.InputDevice(path) for path in self.device_paths if os.access(path, os.R_OK)]
        if not self.devices:
            raise RuntimeError("No readable /dev/input/event* devices found")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, args=(callback,), daemon=True)
        self._thread.start()

    def stop_capture(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None
        for device in self.devices:
            try:
                device.close()
            except Exception:
                pass
        self.devices = []

    def emit(self, event: MacroEvent) -> None:
        ui = self._ensure_uinput()
        e = self.ecodes
        if event.kind == "key" and event.key:
            code = self._key_code(event.key)
            value = 1 if event.action == "press" else 0
            ui.write(e.EV_KEY, code, value)
            ui.syn()
        elif event.kind == "mouse":
            if event.dx:
                ui.write(e.EV_REL, e.REL_X, event.dx)
            if event.dy:
                ui.write(e.EV_REL, e.REL_Y, event.dy)
            if event.x is not None and event.y is not None:
                ui.write(e.EV_ABS, e.ABS_X, event.x)
                ui.write(e.EV_ABS, e.ABS_Y, event.y)
            if event.button and event.action in {"press", "release"}:
                ui.write(e.EV_KEY, self._button_code(event.button), 1 if event.action == "press" else 0)
            ui.syn()
        elif event.kind == "wheel":
            if event.dy:
                ui.write(e.EV_REL, e.REL_WHEEL, event.dy)
            if event.dx:
                ui.write(e.EV_REL, e.REL_HWHEEL, event.dx)
            ui.syn()

    def start_hotkeys(self, callback: HotkeyCallback) -> None:
        self._hotkey_callback = callback

    def stop_hotkeys(self) -> None:
        self._hotkey_callback = None
        self._pressed.clear()

    def close(self) -> None:
        super().close()
        if self.ui:
            self.ui.close()
            self.ui = None

    def _capture_loop(self, callback: EventCallback) -> None:
        while not self._stop_event.is_set():
            readable, _, _ = select.select(self.devices, [], [], 0.1)
            for device in readable:
                for event in device.read():
                    macro_event = self._convert_event(event)
                    if macro_event:
                        self._update_hotkeys(macro_event)
                        callback(macro_event)

    def _convert_event(self, event: object) -> MacroEvent | None:
        e = self.ecodes
        event_type = getattr(event, "type")
        code = getattr(event, "code")
        value = getattr(event, "value")
        if event_type == e.EV_KEY:
            name = e.KEY.get(code) or e.BTN.get(code) or str(code)
            if isinstance(name, list):
                name = name[0]
            text = str(name).replace("KEY_", "").replace("BTN_", "").lower()
            if str(name).startswith("BTN_"):
                return MacroEvent(0, "mouse", "press" if value else "release", button=text)
            return MacroEvent(0, "key", "press" if value else "release", key=EVDEV_KEY_NAMES.get(text, text))
        if event_type == e.EV_REL:
            if code == e.REL_X:
                return MacroEvent(0, "mouse", "move", dx=int(value))
            if code == e.REL_Y:
                return MacroEvent(0, "mouse", "move", dy=int(value))
            if code in {e.REL_WHEEL, getattr(e, "REL_HWHEEL", -1)}:
                return MacroEvent(0, "wheel", "scroll", dy=int(value) if code == e.REL_WHEEL else 0, dx=int(value) if code != e.REL_WHEEL else 0)
        if event_type == e.EV_ABS and code in {e.ABS_X, e.ABS_Y}:
            return MacroEvent(0, "mouse", "move", x=int(value) if code == e.ABS_X else None, y=int(value) if code == e.ABS_Y else None)
        return None

    def _update_hotkeys(self, event: MacroEvent) -> None:
        if not self._hotkey_callback or event.kind != "key" or not event.key:
            return
        key = event.key.lower()
        if event.action == "press":
            self._pressed.add(key)
            self._hotkey_callback(frozenset(self._pressed))
        elif event.action == "release":
            self._pressed.discard(key)

    def _ensure_uinput(self) -> object:
        if self.ui:
            return self.ui
        e = self.ecodes
        capabilities = {
            e.EV_KEY: [
                e.KEY_A,
                e.KEY_B,
                e.KEY_C,
                e.KEY_D,
                e.KEY_E,
                e.KEY_F,
                e.KEY_G,
                e.KEY_H,
                e.KEY_I,
                e.KEY_J,
                e.KEY_K,
                e.KEY_L,
                e.KEY_M,
                e.KEY_N,
                e.KEY_O,
                e.KEY_P,
                e.KEY_Q,
                e.KEY_R,
                e.KEY_S,
                e.KEY_T,
                e.KEY_U,
                e.KEY_V,
                e.KEY_W,
                e.KEY_X,
                e.KEY_Y,
                e.KEY_Z,
                e.KEY_0,
                e.KEY_1,
                e.KEY_2,
                e.KEY_3,
                e.KEY_4,
                e.KEY_5,
                e.KEY_6,
                e.KEY_7,
                e.KEY_8,
                e.KEY_9,
                e.KEY_LEFTCTRL,
                e.KEY_LEFTSHIFT,
                e.KEY_LEFTALT,
                e.KEY_LEFTMETA,
                e.KEY_ENTER,
                e.KEY_ESC,
                e.KEY_SPACE,
                e.KEY_TAB,
                e.KEY_PAUSE,
                e.KEY_SCROLLLOCK,
                e.BTN_LEFT,
                e.BTN_RIGHT,
                e.BTN_MIDDLE,
            ],
            e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, getattr(e, "REL_HWHEEL", e.REL_WHEEL)],
            e.EV_ABS: [e.ABS_X, e.ABS_Y],
        }
        self.ui = self.UInput(capabilities, name="tiny-macro-virtual-input")
        return self.ui

    def _key_code(self, key: str) -> int:
        e = self.ecodes
        lookup = KEY_ALIASES.get(key.lower(), f"KEY_{key.upper()}")
        return int(getattr(e, lookup))

    def _button_code(self, button: str) -> int:
        e = self.ecodes
        lookup = BUTTON_ALIASES.get(button.lower(), f"BTN_{button.upper()}")
        return int(getattr(e, lookup))
