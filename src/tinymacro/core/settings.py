from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Literal

from .hotkeys import HotkeySet
from tinymacro.notifications.config import NotificationSettings

ThemeName = Literal["system", "light", "dark"]

# Built-in theme presets. "monochrome" is the default and keeps the original
# black/white/gray identity; the others only add an accent hue on top of it.
THEME_PRESETS = ("monochrome", "slate", "amber", "emerald", "violet")


def default_config_path() -> Path:
    base = Path.home() / ".config" / "tiny-macro"
    return base / "settings.json"


@dataclass(slots=True)
class Settings:
    theme: ThemeName = "system"
    backend: str = "auto"
    always_on_top: bool = True
    debug_mode: bool = False
    skip_final_click: bool = True
    loop_count: int = 1
    speed: float = 1.0
    # Appearance
    theme_preset: str = "monochrome"
    accent_color: str = ""  # empty keeps the monochrome accent (black/white)
    # Path to an active custom .tmactheme; empty uses the built-in preset above.
    active_theme: str = ""
    compact_mode: bool = True
    animations: bool = True
    ui_sounds: bool = True  # subtle hover/click feedback sounds
    tray_enabled: bool = True
    check_updates_on_startup: bool = True
    ui_scale: float = 1.0  # font/scale multiplier for accessibility
    density: str = "comfortable"  # "comfortable" | "compact" control padding
    ui_variant: str = "classic"  # "classic" toolbar UI or "studio" docked UI
    # Capture / playback tuning
    move_min_interval_ms: int = 0
    humanize_jitter_ms: int = 0
    # A short settling pause inserted between loop iterations so each loop starts
    # from a clean, fresh state instead of blurring into the next. ``loop_gap_ms``
    # is the pause length; ``loop_gap_enabled`` toggles it on/off (default on).
    loop_gap_enabled: bool = True
    loop_gap_ms: int = 40
    # Studio: put the target window back to its original size/position on undock
    # (remembered at dock time). Off leaves it filling the aperture.
    restore_window_on_undock: bool = True
    # Studio dock aperture aspect lock: "free" (fill), "16:9", or "match" (the
    # docked window's own aspect ratio).
    studio_aspect: str = "free"
    # First-run guided tour: set once the user completes or skips onboarding.
    onboarding_seen: bool = False
    # Recording quality-of-life
    record_countdown: int = 0  # seconds counted down before capture starts
    auto_trim_leading: bool = False  # drop idle time before the first action
    # Reliability
    autosave_seconds: int = 30
    log_to_file: bool = True
    # Security: allow "run command / Python" steps to execute. Off by default.
    allow_code_execution: bool = False
    hotkeys: HotkeySet = field(default_factory=HotkeySet)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)

    # ``webhook`` remains a convenience alias to the Discord channel so existing
    # code/tests keep working after the notification system was generalized.
    @property
    def webhook(self):  # type: ignore[override]
        return self.notifications.discord

    @webhook.setter
    def webhook(self, value) -> None:
        self.notifications.discord = value

    @property
    def effective_loop_gap_ns(self) -> int:
        """Playback gap between loops in ns — zero when the toggle is off."""
        return self.loop_gap_ms * 1_000_000 if self.loop_gap_enabled else 0

    def validate(self) -> None:
        if self.theme not in {"system", "light", "dark"}:
            raise ValueError("Invalid theme")
        if self.theme_preset not in THEME_PRESETS:
            raise ValueError("Invalid theme preset")
        if self.accent_color:
            _validate_hex(self.accent_color)
        if self.loop_count < 0:
            raise ValueError("Loop count must be zero or positive")
        if self.speed <= 0:
            raise ValueError("Speed must be positive")
        if self.move_min_interval_ms < 0:
            raise ValueError("Move sampling interval must be zero or positive")
        if self.humanize_jitter_ms < 0:
            raise ValueError("Humanize jitter must be zero or positive")
        if self.loop_gap_ms < 0:
            raise ValueError("Loop gap must be zero or positive")
        if self.record_countdown < 0:
            raise ValueError("Record countdown must be zero or positive")
        if not (0.5 <= self.ui_scale <= 2.0):
            raise ValueError("UI scale must be between 0.5 and 2.0")
        if self.density not in ("comfortable", "compact"):
            raise ValueError("Density must be 'comfortable' or 'compact'")
        if self.ui_variant not in ("classic", "studio"):
            raise ValueError("UI variant must be 'classic' or 'studio'")
        if self.studio_aspect not in ("free", "16:9", "match"):
            raise ValueError("Studio aspect must be 'free', '16:9', or 'match'")
        if self.autosave_seconds < 0:
            raise ValueError("Autosave interval must be zero or positive")
        self.hotkeys.validate()
        self.notifications.validate()

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 2,
            "theme": self.theme,
            "backend": self.backend,
            "always_on_top": self.always_on_top,
            "debug_mode": self.debug_mode,
            "skip_final_click": self.skip_final_click,
            "loop_count": self.loop_count,
            "speed": self.speed,
            "theme_preset": self.theme_preset,
            "accent_color": self.accent_color,
            "active_theme": self.active_theme,
            "compact_mode": self.compact_mode,
            "animations": self.animations,
            "ui_sounds": self.ui_sounds,
            "tray_enabled": self.tray_enabled,
            "check_updates_on_startup": self.check_updates_on_startup,
            "ui_scale": self.ui_scale,
            "density": self.density,
            "ui_variant": self.ui_variant,
            "move_min_interval_ms": self.move_min_interval_ms,
            "humanize_jitter_ms": self.humanize_jitter_ms,
            "loop_gap_enabled": self.loop_gap_enabled,
            "loop_gap_ms": self.loop_gap_ms,
            "onboarding_seen": self.onboarding_seen,
            "restore_window_on_undock": self.restore_window_on_undock,
            "studio_aspect": self.studio_aspect,
            "record_countdown": self.record_countdown,
            "auto_trim_leading": self.auto_trim_leading,
            "autosave_seconds": self.autosave_seconds,
            "log_to_file": self.log_to_file,
            "allow_code_execution": self.allow_code_execution,
            "hotkeys": self.hotkeys.to_dict(),
            "notifications": self.notifications.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Settings":
        settings = cls(
            theme=str(data.get("theme", "system")),  # type: ignore[arg-type]
            backend=str(data.get("backend", "auto")),
            always_on_top=bool(data.get("always_on_top", True)),
            debug_mode=bool(data.get("debug_mode", False)),
            skip_final_click=bool(data.get("skip_final_click", True)),
            loop_count=int(data.get("loop_count", 1)),
            speed=float(data.get("speed", 1.0)),
            theme_preset=str(data.get("theme_preset", "monochrome")),
            accent_color=str(data.get("accent_color", "")),
            active_theme=str(data.get("active_theme", "")),
            compact_mode=bool(data.get("compact_mode", True)),
            animations=bool(data.get("animations", True)),
            ui_sounds=bool(data.get("ui_sounds", True)),
            tray_enabled=bool(data.get("tray_enabled", True)),
            check_updates_on_startup=bool(data.get("check_updates_on_startup", True)),
            ui_scale=float(data.get("ui_scale", 1.0)),
            density=str(data.get("density", "comfortable")),
            ui_variant=str(data.get("ui_variant", "classic")),
            move_min_interval_ms=int(data.get("move_min_interval_ms", 0)),
            humanize_jitter_ms=int(data.get("humanize_jitter_ms", 0)),
            loop_gap_enabled=bool(data.get("loop_gap_enabled", True)),
            loop_gap_ms=int(data.get("loop_gap_ms", 40)),
            onboarding_seen=bool(data.get("onboarding_seen", False)),
            restore_window_on_undock=bool(data.get("restore_window_on_undock", True)),
            studio_aspect=str(data.get("studio_aspect", "free")),
            record_countdown=int(data.get("record_countdown", 0)),
            auto_trim_leading=bool(data.get("auto_trim_leading", False)),
            autosave_seconds=int(data.get("autosave_seconds", 30)),
            log_to_file=bool(data.get("log_to_file", True)),
            allow_code_execution=bool(data.get("allow_code_execution", False)),
            hotkeys=HotkeySet.from_dict(data.get("hotkeys", {}) if isinstance(data.get("hotkeys"), dict) else {}),
            notifications=_load_notifications(data),
        )
        settings.validate()
        return settings

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or default_config_path()
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path | None = None) -> None:
        path = path or default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.validate()
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def _load_notifications(data: dict[str, object]) -> NotificationSettings:
    if isinstance(data.get("notifications"), dict):
        return NotificationSettings.from_dict(data["notifications"])  # type: ignore[index]
    # Migrate a v1 settings file that only had a bare ``webhook`` block.
    if isinstance(data.get("webhook"), dict):
        return NotificationSettings.from_legacy_webhook(data["webhook"])  # type: ignore[index]
    return NotificationSettings()


def _validate_hex(value: str) -> None:
    text = value.strip().lstrip("#")
    if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
        raise ValueError("Accent color must be a 6-digit hex value like #3b82f6")
