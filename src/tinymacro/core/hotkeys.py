from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

MODIFIERS = {"ctrl", "control", "alt", "shift", "super", "meta"}
MODIFIER_ALIASES = {"control": "ctrl", "meta": "super"}


def normalize_key_name(value: str) -> str:
    value = value.strip().lower()
    value = value.replace(" ", "")
    return MODIFIER_ALIASES.get(value, value)


@dataclass(frozen=True, slots=True)
class Hotkey:
    keys: frozenset[str]

    @classmethod
    def parse(cls, text: str) -> "Hotkey":
        parts = [normalize_key_name(part) for part in text.split("+") if part.strip()]
        if not parts:
            raise ValueError("Hotkey cannot be empty")
        if len(parts) != len(set(parts)):
            raise ValueError("Hotkey contains duplicate keys")
        return cls(frozenset(parts))

    def matches(self, pressed: Iterable[str]) -> bool:
        return self.keys == frozenset(normalize_key_name(key) for key in pressed)

    def is_subset_of(self, pressed: Iterable[str]) -> bool:
        return self.keys.issubset(frozenset(normalize_key_name(key) for key in pressed))

    def __str__(self) -> str:
        ordered = sorted(self.keys, key=lambda key: (key not in ("ctrl", "shift", "alt", "super"), key))
        return "+".join("Ctrl" if key == "ctrl" else key.capitalize() for key in ordered)


@dataclass(slots=True)
class HotkeySet:
    record: Hotkey = field(default_factory=lambda: Hotkey.parse("ctrl+shift+alt+r"))
    play: Hotkey = field(default_factory=lambda: Hotkey.parse("ctrl+shift+alt+p"))
    stop: Hotkey = field(default_factory=lambda: Hotkey.parse("ctrl+shift+alt+s"))
    marker: Hotkey = field(default_factory=lambda: Hotkey.parse("ctrl+shift+alt+m"))
    screenshot: Hotkey = field(default_factory=lambda: Hotkey.parse("ctrl+shift+alt+c"))
    emergency: tuple[Hotkey, ...] = field(
        default_factory=lambda: (
            Hotkey.parse("pause"),
            Hotkey.parse("break"),
            Hotkey.parse("scrolllock"),
        )
    )

    def validate(self) -> None:
        named = {
            "record": self.record,
            "play": self.play,
            "stop": self.stop,
            "marker": self.marker,
            "screenshot": self.screenshot,
            **{f"emergency_{index}": key for index, key in enumerate(self.emergency)},
        }

        seen: dict[frozenset[str], str] = {}
        for name, hotkey in named.items():
            if hotkey.keys in seen:
                raise ValueError(f"Hotkey conflict: {name} conflicts with {seen[hotkey.keys]}")
            seen[hotkey.keys] = name

    def control_hotkeys(self) -> tuple[Hotkey, ...]:
        return (self.record, self.play, self.stop, self.marker, self.screenshot, *self.emergency)

    def to_dict(self) -> dict[str, object]:
        return {
            "record": str(self.record),
            "play": str(self.play),
            "stop": str(self.stop),
            "marker": str(self.marker),
            "screenshot": str(self.screenshot),
            "emergency": [str(key) for key in self.emergency],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "HotkeySet":
        hotkeys = cls(
            record=Hotkey.parse(str(data.get("record", "ctrl+shift+alt+r"))),
            play=Hotkey.parse(str(data.get("play", "ctrl+shift+alt+p"))),
            stop=Hotkey.parse(str(data.get("stop", "ctrl+shift+alt+s"))),
            marker=Hotkey.parse(str(data.get("marker", "ctrl+shift+alt+m"))),
            screenshot=Hotkey.parse(str(data.get("screenshot", "ctrl+shift+alt+c"))),
            emergency=tuple(Hotkey.parse(str(item)) for item in data.get("emergency", ["pause", "break", "scrolllock"])),
        )
        hotkeys.validate()
        return hotkeys
