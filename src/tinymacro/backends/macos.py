"""macOS (Cocoa/Quartz) input backend, with best-effort window docking.

Capture + playback come from the shared :class:`~tinymacro.backends._pynput.
PynputBackend` (pynput → Quartz). Window docking is layered on top:

* **enumeration** uses Quartz ``CGWindowListCopyWindowInfo`` (on-screen, normal
  layer) to list other apps' windows;
* **move/resize** uses the **Accessibility (AX) API** — the only supported way to
  reposition another application's window — matching the AX window by title.

Both docking and input need the app to be granted **Accessibility** (and, for
capture, **Input Monitoring**) under System Settings → Privacy & Security. Every
AX/Quartz call is guarded so a missing grant degrades to "docking unavailable"
instead of raising. Because AX exposes only the full window frame (title bar
included), the docked aperture on macOS includes the title bar.
"""
from __future__ import annotations

from tinymacro.backends._pynput import PynputBackend
from tinymacro.backends.base import BackendCapabilities

PERMISSION_HINT = (
    "macOS blocked global input access. Grant Tiny Macro permission under\n"
    "System Settings → Privacy & Security → Accessibility, and (for recording)\n"
    "Input Monitoring, then quit and reopen the app. When running from source,\n"
    "the permission is attached to your terminal/Python — grant it there."
)


def _load_quartz():
    try:
        import Quartz

        return Quartz
    except Exception:  # noqa: BLE001
        return None


def _load_ax():
    """Return a namespace of AX symbols, or None if unavailable.

    AXUIElement lives in the ApplicationServices framework (HIServices); pyobjc
    exposes it under a couple of import paths across versions, so try each.
    """
    for module_name in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            mod = __import__(module_name, fromlist=["AXUIElementCreateApplication"])
            if hasattr(mod, "AXUIElementCreateApplication"):
                return mod
        except Exception:  # noqa: BLE001
            continue
    return None


class MacBackend(PynputBackend):
    """Global capture, playback, hotkeys, and window docking on macOS."""

    name = "darwin"
    capabilities = BackendCapabilities(
        capture=True, playback=True, global_hotkeys=True, requires_privileges=True
    )

    def __init__(self) -> None:
        super().__init__()
        # handle (CGWindowNumber) -> (pid, title) captured during list_windows,
        # so move/resize can find the matching AX window later.
        self._window_index: dict[int, tuple[int, str]] = {}

    def _ensure_permissions(self) -> None:
        try:  # pragma: no cover - exercised only on a real macOS host
            from pynput import keyboard  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "pynput/pyobjc is required for the macOS backend. Install with "
                "`pip install \"tiny-macro\" pyobjc-framework-Quartz`.\n\n" + PERMISSION_HINT
            ) from exc

    # -- window docking -------------------------------------------------------
    def supports_docking(self) -> bool:
        return _load_quartz() is not None and _load_ax() is not None

    def list_windows(self) -> list[tuple[int, str]]:
        Quartz = _load_quartz()
        if Quartz is None:
            return []
        try:
            import os

            options = (
                Quartz.kCGWindowListOptionOnScreenOnly
                | Quartz.kCGWindowListExcludeDesktopElements
            )
            infos = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
            own_pid = os.getpid()
            results: list[tuple[int, str]] = []
            self._window_index.clear()
            for info in infos:
                if int(info.get("kCGWindowLayer", 0)) != 0:
                    continue  # only normal, top-layer app windows
                pid = int(info.get("kCGWindowOwnerPID", 0))
                if pid == own_pid or pid == 0:
                    continue
                number = int(info.get("kCGWindowNumber", 0))
                owner = str(info.get("kCGWindowOwnerName", "") or "")
                name = str(info.get("kCGWindowName", "") or "")
                title = f"{owner} — {name}" if name else owner
                if not title.strip():
                    continue
                self._window_index[number] = (pid, name)
                results.append((number, title))
            return results
        except Exception:  # noqa: BLE001
            return []

    def _ax_window(self, handle: int):
        """Return the AXUIElement window for ``handle``, or None."""
        ax = _load_ax()
        if ax is None:
            return None
        entry = self._window_index.get(int(handle))
        if entry is None:
            return None
        pid, want_title = entry
        try:
            app = ax.AXUIElementCreateApplication(pid)
            err, windows = ax.AXUIElementCopyAttributeValue(app, "AXWindows", None)
            if err != 0 or not windows:
                return None
            if want_title:
                for win in windows:
                    terr, wtitle = ax.AXUIElementCopyAttributeValue(win, "AXTitle", None)
                    if terr == 0 and str(wtitle or "") == want_title:
                        return win
            return windows[0]  # fall back to the app's first/frontmost window
        except Exception:  # noqa: BLE001
            return None

    def window_client_rect(self, handle: int) -> tuple[int, int, int, int] | None:
        ax = _load_ax()
        win = self._ax_window(handle)
        if ax is None or win is None:
            return None
        try:
            Quartz = _load_quartz()
            perr, pos_val = ax.AXUIElementCopyAttributeValue(win, "AXPosition", None)
            serr, size_val = ax.AXUIElementCopyAttributeValue(win, "AXSize", None)
            if perr != 0 or serr != 0:
                return None
            ok_p, point = ax.AXValueGetValue(pos_val, Quartz.kAXValueCGPointType, Quartz.CGPoint())
            ok_s, size = ax.AXValueGetValue(size_val, Quartz.kAXValueCGSizeType, Quartz.CGSize())
            if not (ok_p and ok_s):
                return None
            return (int(point.x), int(point.y), int(size.width), int(size.height))
        except Exception:  # noqa: BLE001
            return None

    def move_resize_window(self, handle: int, left: int, top: int, width: int, height: int) -> bool:
        ax = _load_ax()
        win = self._ax_window(handle)
        if ax is None or win is None or width <= 0 or height <= 0:
            return False
        try:
            Quartz = _load_quartz()
            point = Quartz.CGPoint(x=float(left), y=float(top))
            size = Quartz.CGSize(width=float(width), height=float(height))
            pos_val = ax.AXValueCreate(Quartz.kAXValueCGPointType, point)
            size_val = ax.AXValueCreate(Quartz.kAXValueCGSizeType, size)
            ax.AXUIElementSetAttributeValue(win, "AXPosition", pos_val)
            ax.AXUIElementSetAttributeValue(win, "AXSize", size_val)
            return True
        except Exception:  # noqa: BLE001
            return False
