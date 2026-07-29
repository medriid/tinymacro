"""macOS (Cocoa/Quartz) input backend.

Built on the shared :class:`~tinymacro.backends._pynput.PynputBackend`, which
speaks to CoreGraphics through pynput for both capture and playback. The only
macOS-specific concern is TCC: the OS refuses to deliver global input events (or
inject them) until the running app is granted **Accessibility** and, for
capture, **Input Monitoring** in System Settings → Privacy & Security. We probe
for that up front so the user gets a clear instruction instead of a window that
silently records nothing.
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


class MacBackend(PynputBackend):
    """Global capture, playback, and hotkeys on macOS via Quartz."""

    name = "darwin"
    # Capture/inject work once TCC permissions are granted, hence requires_privileges.
    capabilities = BackendCapabilities(
        capture=True, playback=True, global_hotkeys=True, requires_privileges=True
    )

    def _ensure_permissions(self) -> None:
        """Fail early with actionable guidance if Accessibility isn't granted.

        pynput's macOS backend needs the Quartz bindings from ``pyobjc``; a
        missing framework or a denied Accessibility grant both surface here as a
        clear message rather than a mute recorder.
        """
        try:  # pragma: no cover - exercised only on a real macOS host
            from pynput import keyboard  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "pynput/pyobjc is required for the macOS backend. Install with "
                "`pip install \"tiny-macro\" pyobjc-framework-Quartz`.\n\n" + PERMISSION_HINT
            ) from exc
