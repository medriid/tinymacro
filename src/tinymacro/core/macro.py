from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .events import MacroEvent

FORMAT_VERSION = 1
NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass(slots=True)
class Macro:
    events: list[MacroEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    backend: str = "unknown"
    screen_geometry: str = ""
    keyboard_layout: str = ""
    name: str = "Untitled"

    @property
    def duration_ns(self) -> int:
        if not self.events:
            return 0
        return max(event.timestamp_ns for event in self.events)

    @property
    def duration_s(self) -> float:
        return self.duration_ns / NANOSECONDS_PER_SECOND

    def sorted_events(self) -> list[MacroEvent]:
        return sorted(self.events, key=lambda event: event.timestamp_ns)

    def normalized(self) -> "Macro":
        events = self.sorted_events()
        if not events:
            return self.copy_with(events=[])
        start = events[0].timestamp_ns
        return self.copy_with(events=[event.shifted(-start) for event in events])

    def trim_trailing_idle(self, max_idle_ns: int = 50_000_000) -> "Macro":
        events = self.sorted_events()
        if not events:
            return self.copy_with(events=[])
        last_meaningful = events[-1].timestamp_ns
        end_ns = min(self.duration_ns, last_meaningful + max_idle_ns)
        return self.copy_with(events=[event for event in events if event.timestamp_ns <= end_ns]).normalized()

    def trim_range(self, start_ns: int, end_ns: int) -> "Macro":
        if start_ns < 0 or end_ns < start_ns:
            raise ValueError("Invalid trim range")
        events = [
            event.shifted(-start_ns)
            for event in self.sorted_events()
            if start_ns <= event.timestamp_ns <= end_ns
        ]
        return self.copy_with(events=events).normalized()

    def delete_indices(self, indices: set[int]) -> "Macro":
        events = [event for idx, event in enumerate(self.sorted_events()) if idx not in indices]
        return self.copy_with(events=events).normalized()

    def scale_timing(self, factor: float) -> "Macro":
        if factor <= 0:
            raise ValueError("Timing scale must be positive")
        return self.copy_with(events=[event.scaled(factor) for event in self.sorted_events()]).normalized()

    def copy_with(self, **changes: Any) -> "Macro":
        data = {
            "events": list(self.events),
            "created_at": self.created_at,
            "backend": self.backend,
            "screen_geometry": self.screen_geometry,
            "keyboard_layout": self.keyboard_layout,
            "name": self.name,
        }
        data.update(changes)
        return Macro(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "tiny-macro",
            "version": FORMAT_VERSION,
            "created_at": self.created_at,
            "name": self.name,
            "metadata": {
                "backend": self.backend,
                "screen_geometry": self.screen_geometry,
                "keyboard_layout": self.keyboard_layout,
                "duration_ns": self.duration_ns,
                "event_count": len(self.events),
            },
            "events": [event.to_dict() for event in self.sorted_events()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Macro":
        if data.get("format") != "tiny-macro":
            raise ValueError("Not a tiny-macro file")
        if int(data.get("version", 0)) > FORMAT_VERSION:
            raise ValueError("Macro file was created by a newer version")
        metadata = data.get("metadata", {})
        return cls(
            events=[MacroEvent.from_dict(item) for item in data.get("events", [])],
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            backend=metadata.get("backend", "unknown"),
            screen_geometry=metadata.get("screen_geometry", ""),
            keyboard_layout=metadata.get("keyboard_layout", ""),
            name=data.get("name", "Untitled"),
        ).normalized()

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Macro":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
