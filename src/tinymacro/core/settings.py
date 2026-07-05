from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Literal

from .hotkeys import HotkeySet
from tinymacro.notifications.discord import WebhookSettings

ThemeName = Literal["system", "light", "dark"]


def default_config_path() -> Path:
    base = Path.home() / ".config" / "tiny-macro"
    return base / "settings.json"


@dataclass(slots=True)
class Settings:
    theme: ThemeName = "system"
    backend: str = "auto"
    always_on_top: bool = True
    skip_final_click: bool = True
    loop_count: int = 1
    speed: float = 1.0
    hotkeys: HotkeySet = field(default_factory=HotkeySet)
    webhook: WebhookSettings = field(default_factory=WebhookSettings)

    def validate(self) -> None:
        if self.theme not in {"system", "light", "dark"}:
            raise ValueError("Invalid theme")
        if self.loop_count < 0:
            raise ValueError("Loop count must be zero or positive")
        if self.speed <= 0:
            raise ValueError("Speed must be positive")
        self.hotkeys.validate()
        self.webhook.validate()

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "theme": self.theme,
            "backend": self.backend,
            "always_on_top": self.always_on_top,
            "skip_final_click": self.skip_final_click,
            "loop_count": self.loop_count,
            "speed": self.speed,
            "hotkeys": self.hotkeys.to_dict(),
            "webhook": self.webhook.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Settings":
        settings = cls(
            theme=str(data.get("theme", "system")),  # type: ignore[arg-type]
            backend=str(data.get("backend", "auto")),
            always_on_top=bool(data.get("always_on_top", True)),
            skip_final_click=bool(data.get("skip_final_click", True)),
            loop_count=int(data.get("loop_count", 1)),
            speed=float(data.get("speed", 1.0)),
            hotkeys=HotkeySet.from_dict(data.get("hotkeys", {}) if isinstance(data.get("hotkeys"), dict) else {}),
            webhook=WebhookSettings.from_dict(data.get("webhook", {}) if isinstance(data.get("webhook"), dict) else {}),
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
