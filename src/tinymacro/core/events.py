from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

EventKind = Literal["key", "mouse", "wheel"]
EventAction = Literal["press", "release", "move", "scroll"]


@dataclass(frozen=True, slots=True)
class MacroEvent:
    """A normalized input event stored at a monotonic offset in nanoseconds."""

    timestamp_ns: int
    kind: EventKind
    action: EventAction
    key: str | None = None
    button: str | None = None
    x: int | None = None
    y: int | None = None
    dx: int = 0
    dy: int = 0

    def shifted(self, delta_ns: int) -> "MacroEvent":
        return MacroEvent(
            timestamp_ns=max(0, self.timestamp_ns + delta_ns),
            kind=self.kind,
            action=self.action,
            key=self.key,
            button=self.button,
            x=self.x,
            y=self.y,
            dx=self.dx,
            dy=self.dy,
        )

    def scaled(self, factor: float) -> "MacroEvent":
        return MacroEvent(
            timestamp_ns=max(0, int(self.timestamp_ns * factor)),
            kind=self.kind,
            action=self.action,
            key=self.key,
            button=self.button,
            x=self.x,
            y=self.y,
            dx=self.dx,
            dy=self.dy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "kind": self.kind,
            "action": self.action,
            "key": self.key,
            "button": self.button,
            "x": self.x,
            "y": self.y,
            "dx": self.dx,
            "dy": self.dy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroEvent":
        return cls(
            timestamp_ns=int(data["timestamp_ns"]),
            kind=data["kind"],
            action=data["action"],
            key=data.get("key"),
            button=data.get("button"),
            x=data.get("x"),
            y=data.get("y"),
            dx=int(data.get("dx", 0)),
            dy=int(data.get("dy", 0)),
        )
