"""Xorg backend: capture/playback via pynput, window docking via EWMH.

The docking methods talk to the window manager through the standard EWMH/ICCCM
protocol using ``python-xlib`` (already present wherever pynput's X backend runs).
They're best-effort: every X call is guarded so an uncooperative WM degrades to
"docking unavailable" rather than crashing. Tested against EWMH-compliant WMs
(Mutter, KWin, Xfwm, i3); exotic WMs may ignore the move/resize request.
"""
from __future__ import annotations

import os

from tinymacro.backends._pynput import PynputBackend, _button_name, _key_name  # noqa: F401 (re-export)
from tinymacro.backends.base import BackendCapabilities


class X11Backend(PynputBackend):
    """Xorg capture + playback via pynput, plus EWMH window docking."""

    name = "x11"
    capabilities = BackendCapabilities(capture=True, playback=True, global_hotkeys=True)

    def __init__(self) -> None:
        super().__init__()
        self._display = None  # lazily opened Xlib display for docking

    # -- window docking (EWMH) ------------------------------------------------
    def _xlib(self):
        """Return (Xlib module, open Display) or (None, None) if unavailable."""
        try:
            import Xlib
            from Xlib import display

            if self._display is None:
                self._display = display.Display()
            return Xlib, self._display
        except Exception:  # noqa: BLE001 - no X, no python-xlib, bad $DISPLAY
            return None, None

    def supports_docking(self) -> bool:
        xlib, disp = self._xlib()
        return disp is not None

    def _atom(self, disp, name: str) -> int:
        return disp.intern_atom(name)

    def _prop(self, window, atom: int):
        try:
            reply = window.get_full_property(atom, 0)
        except Exception:  # noqa: BLE001
            return None
        return reply.value if reply is not None else None

    def list_windows(self) -> list[tuple[int, str]]:
        xlib, disp = self._xlib()
        if disp is None:
            return []
        try:
            root = disp.screen().root
            net_client_list = self._atom(disp, "_NET_CLIENT_LIST")
            ids = self._prop(root, net_client_list) or []
            net_name = self._atom(disp, "_NET_WM_NAME")
            net_pid = self._atom(disp, "_NET_WM_PID")
            own_pid = os.getpid()
            results: list[tuple[int, str]] = []
            for wid in ids:
                win = disp.create_resource_object("window", int(wid))
                pid_val = self._prop(win, net_pid)
                if pid_val and int(pid_val[0]) == own_pid:
                    continue  # skip our own windows
                title = self._prop(win, net_name)
                if title is None:
                    try:
                        title = win.get_wm_name()  # legacy WM_NAME fallback
                    except Exception:  # noqa: BLE001
                        title = None
                text = title.decode("utf-8", "replace") if isinstance(title, (bytes, bytearray)) else str(title or "")
                if not text.strip():
                    continue
                results.append((int(wid), text))
            return results
        except Exception:  # noqa: BLE001
            return []

    def _frame_extents(self, disp, win) -> tuple[int, int, int, int]:
        """(left, right, top, bottom) decoration thickness, or zeros if unknown."""
        ext = self._prop(win, self._atom(disp, "_NET_FRAME_EXTENTS"))
        if ext and len(ext) >= 4:
            return int(ext[0]), int(ext[1]), int(ext[2]), int(ext[3])
        return 0, 0, 0, 0

    def window_client_rect(self, handle: int) -> tuple[int, int, int, int] | None:
        xlib, disp = self._xlib()
        if disp is None:
            return None
        try:
            win = disp.create_resource_object("window", int(handle))
            geom = win.get_geometry()
            root = disp.screen().root
            coords = win.translate_coords(root, 0, 0)
            # translate_coords gives the child's origin relative to root; negate.
            abs_x = -coords.x
            abs_y = -coords.y
            return (int(abs_x), int(abs_y), int(geom.width), int(geom.height))
        except Exception:  # noqa: BLE001
            return None

    def move_resize_window(self, handle: int, left: int, top: int, width: int, height: int) -> bool:
        xlib, disp = self._xlib()
        if disp is None or width <= 0 or height <= 0:
            return False
        try:
            from Xlib import X, Xutil  # noqa: F401

            win = disp.create_resource_object("window", int(handle))
            root = disp.screen().root

            # Un-maximise first so the geometry request isn't ignored by the WM.
            self._send_wm_state(disp, root, win, "_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_MAXIMIZED_VERT")

            # Position the frame so the *client* area fills the requested rect.
            fl, fr, ft, fb = self._frame_extents(disp, win)
            gravity_static = 10  # StaticGravity
            source = 1          # normal application
            flags = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11) | gravity_static | (source << 12)
            data = [flags, int(left), int(top), int(width), int(height)]
            self._client_message(disp, root, win, "_NET_MOVERESIZE_WINDOW", data)

            # Fallback direct configure for WMs that ignore the message above.
            win.configure(x=int(left), y=int(top), width=int(width), height=int(height))
            disp.sync()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _client_message(self, disp, root, win, message: str, data: list[int]) -> None:
        from Xlib import X
        from Xlib.protocol import event

        data = (data + [0, 0, 0, 0, 0])[:5]
        ev = event.ClientMessage(
            window=win, client_type=self._atom(disp, message), data=(32, data)
        )
        mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
        root.send_event(ev, event_mask=mask)

    def _send_wm_state(self, disp, root, win, *states: str) -> None:
        # _NET_WM_STATE: action=0 (remove), then up to two state atoms.
        for i in range(0, len(states), 2):
            pair = states[i : i + 2]
            data = [0, self._atom(disp, pair[0]), self._atom(disp, pair[1]) if len(pair) > 1 else 0, 1, 0]
            self._client_message(disp, root, win, "_NET_WM_STATE", data)

    def close(self) -> None:
        super().close()
        if self._display is not None:
            try:
                self._display.close()
            except Exception:  # noqa: BLE001
                pass
            self._display = None
