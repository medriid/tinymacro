"""Subtle UI feedback sounds (hover / click).

Wraps ``QSoundEffect`` behind a tiny singleton so the whole app can call
``ui_sounds().hover()`` / ``.click()`` without every widget owning a player.
Everything degrades to a silent no-op when QtMultimedia is unavailable, the
assets are missing, or the user turns UI sounds off in Preferences.

The samples are deliberately quiet and short (~150 ms). Hover is throttled so
sweeping the pointer across a toolbar doesn't machine-gun the speaker.
"""
from __future__ import annotations

from pathlib import Path
import time

SOUND_DIR = Path(__file__).resolve().parent / "sounds"

# Hover is the quieter of the two: it fires constantly, so it must sit under the
# click, which should feel like the definite "yes, that registered" response.
HOVER_VOLUME = 0.22
CLICK_VOLUME = 0.45
# Minimum gap between hover blips (seconds). Long enough to stop a rapid sweep
# from stacking sounds, short enough that deliberate hovers always respond.
HOVER_THROTTLE_S = 0.07


class UiSounds:
    """Lazily-loaded hover/click effects with a global on/off switch."""

    def __init__(self) -> None:
        self._enabled = True
        self._loaded = False
        self._hover = None
        self._click = None
        self._last_hover = 0.0

    # -- configuration --------------------------------------------------------
    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        """True when the effects actually loaded (QtMultimedia + assets present)."""
        self._ensure_loaded()
        return self._hover is not None or self._click is not None

    # -- playback -------------------------------------------------------------
    def hover(self) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        if now - self._last_hover < HOVER_THROTTLE_S:
            return
        self._last_hover = now
        self._play(self._effect("hover"))

    def click(self) -> None:
        if not self._enabled:
            return
        self._play(self._effect("click"))

    # -- internals ------------------------------------------------------------
    def _effect(self, name: str):
        self._ensure_loaded()
        return self._hover if name == "hover" else self._click

    @staticmethod
    def _play(effect) -> None:
        if effect is None:
            return
        try:
            effect.play()
        except Exception:  # noqa: BLE001 - audio must never break the UI
            pass

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True  # only ever try once; a failure stays silent
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QSoundEffect
            from PyQt6.QtWidgets import QApplication

            if QApplication.instance() is None:
                self._loaded = False  # retry once there's an app to own the effects
                return

            def make(filename: str, volume: float):
                path = SOUND_DIR / filename
                if not path.is_file():
                    return None
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setVolume(volume)
                return effect

            self._hover = make("hover.wav", HOVER_VOLUME)
            self._click = make("click.wav", CLICK_VOLUME)
        except Exception:  # noqa: BLE001 - no QtMultimedia backend → stay silent
            self._hover = self._click = None


_instance: UiSounds | None = None


def ui_sounds() -> UiSounds:
    """The process-wide sound player."""
    global _instance
    if _instance is None:
        _instance = UiSounds()
    return _instance
