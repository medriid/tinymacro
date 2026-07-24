from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# ``wait`` is a synthetic step that pauses playback for ``duration_ns`` (plus an
# optional random ``jitter_ns``) without emitting real input. It lets a macro
# carry explicit, editable pauses instead of only implicit timestamp gaps.
EventKind = Literal["key", "mouse", "wheel", "wait"]
EventAction = Literal["press", "release", "move", "scroll", "delay"]

# Bumped alongside macro.FORMAT_VERSION when the on-disk shape grows. New
# optional fields are only written when they differ from their defaults so that
# version-1 readers keep working and version-1 files load unchanged.
DEFAULT_DURATION_NS = 0
DEFAULT_JITTER_NS = 0


@dataclass(frozen=True, slots=True)
class MacroEvent:
    """A normalized input event stored at a monotonic offset in nanoseconds.

    Fields added in format v2 (all optional, default to their v1 behaviour):

    * ``duration_ns`` -- for ``wait`` steps this is the base pause; for ``key``
      press events it may record how long the key was physically held.
    * ``jitter_ns`` -- an upper bound of extra random time added at playback so
      QA/testing playback is not perfectly metronomic.
    * ``note`` -- a free-form human label shown in the editor.
    """

    timestamp_ns: int
    kind: EventKind
    action: EventAction
    key: str | None = None
    button: str | None = None
    x: int | None = None
    y: int | None = None
    dx: int = 0
    dy: int = 0
    duration_ns: int = DEFAULT_DURATION_NS
    jitter_ns: int = DEFAULT_JITTER_NS
    note: str = ""

    # -- construction helpers -------------------------------------------------
    @classmethod
    def wait(cls, timestamp_ns: int, duration_ns: int, jitter_ns: int = 0, note: str = "") -> "MacroEvent":
        return cls(
            timestamp_ns=timestamp_ns,
            kind="wait",
            action="delay",
            duration_ns=max(0, int(duration_ns)),
            jitter_ns=max(0, int(jitter_ns)),
            note=note,
        )

    @property
    def is_input(self) -> bool:
        """True when the event produces real input (i.e. should be emitted)."""
        return self.kind != "wait"

    def replace(self, **changes: Any) -> "MacroEvent":
        data = self.to_dict()
        data.update(changes)
        return MacroEvent.from_dict(data)

    def shifted(self, delta_ns: int) -> "MacroEvent":
        return self._with(timestamp_ns=max(0, self.timestamp_ns + delta_ns))

    def scaled(self, factor: float) -> "MacroEvent":
        return self._with(
            timestamp_ns=max(0, int(self.timestamp_ns * factor)),
            duration_ns=max(0, int(self.duration_ns * factor)),
            jitter_ns=max(0, int(self.jitter_ns * factor)),
        )

    def _with(self, **changes: Any) -> "MacroEvent":
        base = dict(
            timestamp_ns=self.timestamp_ns,
            kind=self.kind,
            action=self.action,
            key=self.key,
            button=self.button,
            x=self.x,
            y=self.y,
            dx=self.dx,
            dy=self.dy,
            duration_ns=self.duration_ns,
            jitter_ns=self.jitter_ns,
            note=self.note,
        )
        base.update(changes)
        return MacroEvent(**base)

    def describe(self) -> str:
        """Short, human-friendly one-line description used in the UI/log."""
        if self.kind == "wait":
            base = self.duration_ns / 1_000_000
            if self.jitter_ns:
                return f"wait {base:.0f}–{base + self.jitter_ns / 1_000_000:.0f} ms"
            return f"wait {base:.0f} ms"
        if self.kind == "key":
            return f"key {self.action} {self.key}"
        if self.kind == "wheel":
            return f"wheel scroll {self.dx},{self.dy}"
        pos = "" if self.x is None else f" @ {self.x},{self.y}"
        if self.action == "move":
            return f"mouse move{pos}"
        return f"mouse {self.action} {self.button or ''}{pos}".rstrip()

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        # Only emit v2 fields when they carry information; keeps files that never
        # use the new features byte-for-byte v1-shaped.
        if self.duration_ns:
            data["duration_ns"] = self.duration_ns
        if self.jitter_ns:
            data["jitter_ns"] = self.jitter_ns
        if self.note:
            data["note"] = self.note
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroEvent":
        kind = data["kind"]
        action = data["action"]
        key = data.get("key")
        button = data.get("button")
        legacy_button = _legacy_mouse_button_from_key(key)
        if kind == "key" and legacy_button:
            kind = "mouse"
            button = legacy_button
            key = None
        return cls(
            timestamp_ns=int(data["timestamp_ns"]),
            kind=kind,
            action=action,
            key=key,
            button=button,
            x=data.get("x"),
            y=data.get("y"),
            dx=int(data.get("dx", 0)),
            dy=int(data.get("dy", 0)),
            duration_ns=int(data.get("duration_ns", DEFAULT_DURATION_NS)),
            jitter_ns=int(data.get("jitter_ns", DEFAULT_JITTER_NS)),
            note=str(data.get("note", "")),
        )


def _legacy_mouse_button_from_key(key: object) -> str | None:
    if not isinstance(key, str):
        return None
    compact = key.replace(" ", "").lower()
    mapping = {
        "('left','mouse')": "left",
        "('right','mouse')": "right",
        "('middle','mouse')": "middle",
        "['left','mouse']": "left",
        "['right','mouse']": "right",
        "['middle','mouse']": "middle",
        "btn_left": "left",
        "btn_right": "right",
        "btn_middle": "middle",
    }
    return mapping.get(compact)
