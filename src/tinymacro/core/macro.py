from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any, Iterable

from .events import MacroEvent

# v2 adds optional per-event fields (duration/jitter/note) and macro-level tags.
# v3 adds the ``image`` (click-image) step.
# v4 adds automation/control steps (run, pixel, window, if/else/endif, loop).
# Readers stay backward compatible: older files load unchanged, and newer keys
# are only written when actually used.
FORMAT_VERSION = 4
NANOSECONDS_PER_SECOND = 1_000_000_000

# Classic macros use absolute screen coordinates and the ".tmacro" extension.
# Studio (docked) macros store window-relative coordinates and use ".tmacd";
# the two are intentionally not interchangeable between the UI variants.
CLASSIC_FORMAT = "tiny-macro"
DOCK_FORMAT = "tiny-macro-dock"
CLASSIC_EXTENSION = ".tmacro"
DOCK_EXTENSION = ".tmacd"


def _event_end_ns(event: MacroEvent) -> int:
    end = event.timestamp_ns
    if event.kind == "wait":
        end += event.duration_ns + event.jitter_ns
    return end


def _is_meaningful_event(event: MacroEvent) -> bool:
    return event.kind != "wait" and not (event.kind == "mouse" and event.action == "move")


def _last_meaningful_event(events: list[MacroEvent]) -> MacroEvent | None:
    return next((event for event in reversed(events) if _is_meaningful_event(event)), None)


def _trim_wait_to_end(event: MacroEvent, end_ns: int) -> MacroEvent:
    max_span = max(0, end_ns - event.timestamp_ns)
    if event.duration_ns + event.jitter_ns <= max_span:
        return event
    duration_ns = min(event.duration_ns, max_span)
    jitter_ns = min(event.jitter_ns, max(0, max_span - duration_ns))
    return event._with(duration_ns=duration_ns, jitter_ns=jitter_ns)


def _trim_events_to_end(events: list[MacroEvent], end_ns: int) -> list[MacroEvent]:
    trimmed: list[MacroEvent] = []
    for event in events:
        if event.timestamp_ns > end_ns:
            continue
        trimmed.append(_trim_wait_to_end(event, end_ns) if event.kind == "wait" else event)
    return trimmed


def _trim_leading_event(event: MacroEvent, cut_ns: int) -> MacroEvent | None:
    if event.kind == "wait":
        end_ns = _event_end_ns(event)
        new_start = max(0, event.timestamp_ns - cut_ns)
        new_end = max(0, end_ns - cut_ns)
        if new_end < new_start:
            return None
        max_span = new_end - new_start
        duration_ns = min(event.duration_ns, max_span)
        jitter_ns = min(event.jitter_ns, max(0, max_span - duration_ns))
        return event._with(timestamp_ns=new_start, duration_ns=duration_ns, jitter_ns=jitter_ns)
    return event.shifted(-cut_ns) if event.timestamp_ns >= cut_ns else event._with(timestamp_ns=0)


@dataclass(slots=True)
class Macro:
    events: list[MacroEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    backend: str = "unknown"
    screen_geometry: str = ""
    keyboard_layout: str = ""
    name: str = "Untitled"
    tags: tuple[str, ...] = ()
    description: str = ""
    # Per-macro playback preferences, restored when the macro is opened.
    speed: float = 1.0
    loop_count: int = 1
    # Studio (docked) macros: relative coordinates + the target-window hint.
    docked: bool = False
    target_window: str = ""

    # -- timing ---------------------------------------------------------------
    @property
    def duration_ns(self) -> int:
        if not self.events:
            return 0
        return max(self._event_end_ns(event) for event in self.events)

    @property
    def duration_s(self) -> float:
        return self.duration_ns / NANOSECONDS_PER_SECOND

    @staticmethod
    def _event_end_ns(event: MacroEvent) -> int:
        return _event_end_ns(event)

    def sorted_events(self) -> list[MacroEvent]:
        return sorted(self.events, key=lambda event: event.timestamp_ns)

    def input_event_count(self) -> int:
        return sum(1 for event in self.events if event.is_input)

    def wait_event_count(self) -> int:
        return sum(1 for event in self.events if event.kind == "wait")

    def image_event_count(self) -> int:
        return sum(1 for event in self.events if event.kind == "image")

    # -- normalization / editing ---------------------------------------------
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
        last_meaningful = _last_meaningful_event(events)
        if last_meaningful is None:
            end_ns = min(self.duration_ns, max_idle_ns)
        else:
            end_ns = min(self.duration_ns, self._event_end_ns(last_meaningful) + max_idle_ns)
        return self.copy_with(events=_trim_events_to_end(events, end_ns)).normalized()

    def trim_leading_idle(self, max_idle_ns: int = 50_000_000) -> "Macro":
        """Drop dead time before the first meaningful action.

        The first event is often just the recorded cursor anchor; this removes
        the gap between it and the first real input so playback starts promptly.
        """
        events = self.sorted_events()
        if len(events) < 2:
            return self.copy_with(events=events).normalized()
        # Find the first event that carries real intent (not a wait or anchor move).
        first_real = next(
            (e for e in events if _is_meaningful_event(e)),
            events[0],
        )
        cut = max(0, first_real.timestamp_ns - max_idle_ns)
        if cut <= 0:
            return self.copy_with(events=events).normalized()
        shifted = [_trim_leading_event(event, cut) for event in events if _event_end_ns(event) >= cut]
        anchors = [
            event._with(timestamp_ns=0)
            for event in events
            if event.kind == "mouse" and event.action == "move" and _event_end_ns(event) < cut
        ]
        shifted = anchors[:1] + [event for event in shifted if event is not None]
        return self.copy_with(events=shifted).normalized()

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

    def replace_event(self, index: int, event: MacroEvent) -> "Macro":
        events = self.sorted_events()
        if not 0 <= index < len(events):
            raise IndexError("Event index out of range")
        events[index] = event
        return self.copy_with(events=events).normalized()

    def insert_wait(self, index: int, duration_ns: int, jitter_ns: int = 0, note: str = "") -> "Macro":
        """Insert a wait step before ``index`` and push later events back."""
        events = self.sorted_events()
        index = max(0, min(index, len(events)))
        at_ns = events[index].timestamp_ns if index < len(events) else self.duration_ns
        wait = MacroEvent.wait(at_ns, duration_ns, jitter_ns, note)
        shifted = [
            event.shifted(duration_ns + jitter_ns) if event.timestamp_ns >= at_ns else event
            for event in events
        ]
        shifted.insert(index, wait)
        return self.copy_with(events=shifted).normalized()

    def insert_event(self, index: int, event: MacroEvent) -> "Macro":
        """Insert a generic point event before ``index`` at that position's time.

        Used by the editor's "insert any event" tools. Like :meth:`insert_image`
        it adds no fixed duration, so later events keep their timestamps.
        """
        events = self.sorted_events()
        index = max(0, min(index, len(events)))
        at_ns = events[index].timestamp_ns if index < len(events) else self.duration_ns
        events.insert(index, event._with(timestamp_ns=at_ns))
        return self.copy_with(events=events).normalized()

    def duplicate_indices(self, indices: set[int] | list[int]) -> "Macro":
        """Insert a copy of each selected event right after it."""
        wanted = {i for i in indices}
        events = self.sorted_events()
        result: list[MacroEvent] = []
        for idx, event in enumerate(events):
            result.append(event)
            if idx in wanted:
                result.append(event._with())  # a distinct copy at the same time
        return self.copy_with(events=result).normalized()

    def wrap_in_loop(self, indices: set[int] | list[int], count: int) -> "Macro":
        """Wrap the selected contiguous range in a loop/endloop block."""
        return self._wrap(indices, MacroEvent.loop_start(0, count), "endloop")

    def wrap_in_if(self, indices: set[int] | list[int], condition: MacroEvent) -> "Macro":
        """Wrap the selected range in an if(condition)/endif block."""
        if condition.kind != "if":
            raise ValueError("wrap_in_if expects an 'if' event")
        return self._wrap(indices, condition, "endif")

    def _wrap(self, indices, opener: MacroEvent, closer_kind: str) -> "Macro":
        events = self.sorted_events()
        chosen = sorted(i for i in indices if 0 <= i < len(events))
        if not chosen:
            return self.copy_with(events=events)
        start_i, end_i = chosen[0], chosen[-1]
        opener = opener._with(timestamp_ns=events[start_i].timestamp_ns)
        closer = MacroEvent.control(events[end_i].timestamp_ns, closer_kind)
        new = events[:start_i] + [opener] + events[start_i:end_i + 1] + [closer] + events[end_i + 1:]
        return self.copy_with(events=new).normalized()

    def move_index(self, index: int, direction: int) -> "Macro":
        """Move the event at ``index`` up (-1) or down (+1) by swapping timestamps.

        The timeline is timestamp-ordered, so reordering means swapping this
        event's time with its neighbour's; a no-op at the ends.
        """
        events = self.sorted_events()
        target = index + direction
        if not (0 <= index < len(events)) or not (0 <= target < len(events)):
            return self.copy_with(events=events)
        a, b = events[index], events[target]
        events[index] = a._with(timestamp_ns=b.timestamp_ns)
        events[target] = b._with(timestamp_ns=a.timestamp_ns)
        return self.copy_with(events=events).normalized()

    def insert_image(self, index: int, event: MacroEvent) -> "Macro":
        """Insert a prebuilt ``image`` step before ``index``.

        Unlike :meth:`insert_wait`, an image step has no fixed duration (its cost
        is decided at playback by the on-screen search), so later events are not
        pushed back. The step takes the timestamp of the event it precedes, and a
        stable sort keeps it just before that event.
        """
        if event.kind != "image":
            raise ValueError("insert_image expects an image event")
        events = self.sorted_events()
        index = max(0, min(index, len(events)))
        at_ns = events[index].timestamp_ns if index < len(events) else self.duration_ns
        placed = event._with(timestamp_ns=at_ns)
        events.insert(index, placed)
        return self.copy_with(events=events).normalized()

    def set_note(self, index: int, note: str) -> "Macro":
        events = self.sorted_events()
        if not 0 <= index < len(events):
            raise IndexError("Event index out of range")
        events[index] = events[index].replace(note=note)
        return self.copy_with(events=events)

    # -- composition ----------------------------------------------------------
    def then(self, other: "Macro", gap_ns: int = 0) -> "Macro":
        """Append ``other`` after this macro, separated by ``gap_ns``."""
        offset = self.duration_ns + max(0, gap_ns)
        combined = self.sorted_events() + [event.shifted(offset) for event in other.sorted_events()]
        return self.copy_with(events=combined).normalized()

    @classmethod
    def chain(cls, macros: Iterable["Macro"], gap_ns: int = 0, name: str = "Chained") -> "Macro":
        result: Macro | None = None
        for macro in macros:
            result = macro.copy_with() if result is None else result.then(macro, gap_ns=gap_ns)
        if result is None:
            return cls(name=name)
        return result.copy_with(name=name)

    def repeated(self, times: int, gap_ns: int = 0) -> "Macro":
        if times < 1:
            raise ValueError("Repeat count must be at least 1")
        return Macro.chain([self] * times, gap_ns=gap_ns, name=self.name)

    def humanized(self, jitter_ns: int, seed: int | None = None) -> "Macro":
        """Add up to ``jitter_ns`` of positive timing jitter to each event.

        This is intended for realistic QA/testing playback, not for defeating
        detection systems. Order is preserved (jitter never reorders events).
        """
        if jitter_ns < 0:
            raise ValueError("Jitter must be zero or positive")
        rng = random.Random(seed)
        cumulative = 0
        events: list[MacroEvent] = []
        for event in self.sorted_events():
            cumulative += rng.randint(0, jitter_ns)
            events.append(event.shifted(cumulative))
        return self.copy_with(events=events).normalized()

    def copy_with(self, **changes: Any) -> "Macro":
        data = {
            "events": list(self.events),
            "created_at": self.created_at,
            "backend": self.backend,
            "screen_geometry": self.screen_geometry,
            "keyboard_layout": self.keyboard_layout,
            "name": self.name,
            "tags": tuple(self.tags),
            "description": self.description,
            "speed": self.speed,
            "loop_count": self.loop_count,
            "docked": self.docked,
            "target_window": self.target_window,
        }
        data.update(changes)
        if "tags" in data:
            data["tags"] = tuple(data["tags"])
        return Macro(**data)

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": DOCK_FORMAT if self.docked else CLASSIC_FORMAT,
            "version": FORMAT_VERSION,
            "created_at": self.created_at,
            "name": self.name,
            "tags": list(self.tags),
            "description": self.description,
            "metadata": {
                "backend": self.backend,
                "screen_geometry": self.screen_geometry,
                "keyboard_layout": self.keyboard_layout,
                "duration_ns": self.duration_ns,
                "event_count": len(self.events),
                "input_event_count": self.input_event_count(),
                "wait_event_count": self.wait_event_count(),
                "speed": self.speed,
                "loop_count": self.loop_count,
                "docked": self.docked,
                "target_window": self.target_window,
            },
            "events": [event.to_dict() for event in self.sorted_events()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Macro":
        fmt = data.get("format")
        if fmt not in (CLASSIC_FORMAT, DOCK_FORMAT):
            raise ValueError("Not a tiny-macro file")
        if int(data.get("version", 0)) > FORMAT_VERSION:
            raise ValueError("Macro file was created by a newer version")
        metadata = data.get("metadata", {})
        raw_tags = data.get("tags", [])
        tags = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, (list, tuple)) else ()
        return cls(
            events=[MacroEvent.from_dict(item) for item in data.get("events", [])],
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            backend=metadata.get("backend", "unknown"),
            screen_geometry=metadata.get("screen_geometry", ""),
            keyboard_layout=metadata.get("keyboard_layout", ""),
            name=data.get("name", "Untitled"),
            tags=tags,
            description=str(data.get("description", "")),
            speed=float(metadata.get("speed", 1.0)),
            loop_count=int(metadata.get("loop_count", 1)),
            docked=bool(metadata.get("docked", fmt == DOCK_FORMAT)),
            target_window=str(metadata.get("target_window", "")),
        ).normalized()

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Macro":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def load_for_variant(cls, path: str | Path, docked: bool) -> "Macro":
        """Load a macro, rejecting it if it doesn't match the UI variant.

        Studio (docked) and classic macros are intentionally incompatible: a
        ``.tmacd`` won't open in the classic UI and a ``.tmacro`` won't open in
        Studio, because their coordinates mean different things.
        """
        macro = cls.load(path)
        if macro.docked != docked:
            wanted = "Studio (.tmacd)" if docked else "classic (.tmacro)"
            got = "Studio (.tmacd)" if macro.docked else "classic (.tmacro)"
            raise ValueError(f"This is a {got} macro; the current UI needs a {wanted} macro.")
        return macro
