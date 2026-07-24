from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from tinymacro.core.settings import Settings


def default_profiles_path() -> Path:
    return Path.home() / ".config" / "tiny-macro" / "profiles.json"


@dataclass(slots=True)
class ProfileStore:
    """Holds several named Settings snapshots and tracks the active one.

    This lets a user keep, say, a "gaming" profile and a "QA" profile with
    different hotkeys, speeds and notification targets, and switch between them.
    """

    profiles: dict[str, Settings] = field(default_factory=lambda: {"Default": Settings()})
    active: str = "Default"
    _path: Path | None = None

    def __post_init__(self) -> None:
        if not self.profiles:
            self.profiles = {"Default": Settings()}
        if self.active not in self.profiles:
            self.active = next(iter(self.profiles))

    @property
    def current(self) -> Settings:
        return self.profiles[self.active]

    def names(self) -> list[str]:
        return list(self.profiles)

    def switch(self, name: str) -> Settings:
        if name not in self.profiles:
            raise KeyError(f"No such profile: {name}")
        self.active = name
        return self.current

    def add(self, name: str, settings: Settings | None = None, activate: bool = True) -> Settings:
        name = name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")
        if name in self.profiles:
            raise ValueError(f"Profile already exists: {name}")
        self.profiles[name] = settings or Settings()
        if activate:
            self.active = name
        return self.profiles[name]

    def duplicate(self, source: str, new_name: str) -> Settings:
        if source not in self.profiles:
            raise KeyError(f"No such profile: {source}")
        clone = Settings.from_dict(self.profiles[source].to_dict())
        return self.add(new_name, clone)

    def rename(self, old: str, new: str) -> None:
        new = new.strip()
        if old not in self.profiles:
            raise KeyError(f"No such profile: {old}")
        if not new or (new != old and new in self.profiles):
            raise ValueError("Invalid or duplicate profile name")
        self.profiles[new] = self.profiles.pop(old)
        if self.active == old:
            self.active = new

    def remove(self, name: str) -> None:
        if name not in self.profiles:
            return
        if len(self.profiles) == 1:
            raise ValueError("Cannot remove the last profile")
        del self.profiles[name]
        if self.active == name:
            self.active = next(iter(self.profiles))

    # -- import / export ------------------------------------------------------
    def export_profile(self, name: str, path: str | Path) -> None:
        if name not in self.profiles:
            raise KeyError(f"No such profile: {name}")
        payload = {"name": name, "settings": self.profiles[name].to_dict()}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_profile(self, path: str | Path, activate: bool = True) -> str:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        raw = data.get("settings", data)
        settings = Settings.from_dict(raw)
        name = str(data.get("name") or Path(path).stem)
        base = name
        counter = 2
        while name in self.profiles:
            name = f"{base} ({counter})"
            counter += 1
        self.profiles[name] = settings
        if activate:
            self.active = name
        return name

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "active": self.active,
            "profiles": {name: settings.to_dict() for name, settings in self.profiles.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProfileStore":
        raw = data.get("profiles", {})
        profiles: dict[str, Settings] = {}
        if isinstance(raw, dict):
            for name, payload in raw.items():
                if isinstance(payload, dict):
                    profiles[str(name)] = Settings.from_dict(payload)
        if not profiles:
            profiles = {"Default": Settings()}
        active = str(data.get("active", next(iter(profiles))))
        return cls(profiles=profiles, active=active)

    @classmethod
    def load(cls, path: Path | None = None) -> "ProfileStore":
        path = path or default_profiles_path()
        store = cls() if not path.exists() else cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        store._path = path
        return store

    def save(self, path: Path | None = None) -> None:
        path = path or self._path or default_profiles_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        self._path = path
