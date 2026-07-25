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
    compact_mode: bool = True
    animations: bool = True
    tray_enabled: bool = True
    ui_scale: float = 1.0  # font/scale multiplier for accessibility
    density: str = "comfortable"  # "comfortable" | "compact" control padding
    # Capture / playback tuning
    move_min_interval_ms: int = 0
    humanize_jitter_ms: int = 0
    # Recording quality-of-life
    record_countdown: int = 0  # seconds counted down before capture starts
    auto_trim_leading: bool = False  # drop idle time before the first action
    # Reliability
    autosave_seconds: int = 30
    log_to_file: bool = True
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
        if self.record_countdown < 0:
            raise ValueError("Record countdown must be zero or positive")
        if not (0.5 <= self.ui_scale <= 2.0):
            raise ValueError("UI scale must be between 0.5 and 2.0")
        if self.density not in ("comfortable", "compact"):
            raise ValueError("Density must be 'comfortable' or 'compact'")
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
            "compact_mode": self.compact_mode,
            "animations": self.animations,
            "tray_enabled": self.tray_enabled,
            "ui_scale": self.ui_scale,
            "density": self.density,
            "move_min_interval_ms": self.move_min_interval_ms,
            "humanize_jitter_ms": self.humanize_jitter_ms,
            "record_countdown": self.record_countdown,
            "auto_trim_leading": self.auto_trim_leading,
            "autosave_seconds": self.autosave_seconds,
            "log_to_file": self.log_to_file,
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
            compact_mode=bool(data.get("compact_mode", True)),
            animations=bool(data.get("animations", True)),
            tray_enabled=bool(data.get("tray_enabled", True)),
            ui_scale=float(data.get("ui_scale", 1.0)),
            density=str(data.get("density", "comfortable")),
            move_min_interval_ms=int(data.get("move_min_interval_ms", 0)),
            humanize_jitter_ms=int(data.get("humanize_jitter_ms", 0)),
            record_countdown=int(data.get("record_countdown", 0)),
            auto_trim_leading=bool(data.get("auto_trim_leading", False)),
            autosave_seconds=int(data.get("autosave_seconds", 30)),
            log_to_file=bool(data.get("log_to_file", True)),
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
