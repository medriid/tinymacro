from __future__ import annotations

from tinymacro.backends._pynput import PynputBackend, _button_name, _key_name  # noqa: F401 (re-export)
from tinymacro.backends.base import BackendCapabilities


class X11Backend(PynputBackend):
    """Xorg capture + playback via pynput (X records/injects freely for local apps)."""

    name = "x11"
    capabilities = BackendCapabilities(capture=True, playback=True, global_hotkeys=True)
