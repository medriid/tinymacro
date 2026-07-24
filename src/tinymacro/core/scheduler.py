from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Literal

ScheduleKind = Literal["interval", "daily", "once"]


def default_schedule_path() -> Path:
    return Path.home() / ".config" / "tiny-macro" / "schedules.json"


@dataclass(slots=True)
class Schedule:
    """A rule for running a macro automatically.

    * ``interval`` -- every ``interval_seconds`` seconds.
    * ``daily``    -- once per day at ``at_hour``:``at_minute`` (local time).
    * ``once``     -- a single run at a specific ``run_at`` timestamp.
    """

    macro_path: str
    kind: ScheduleKind = "interval"
    interval_seconds: int = 3600
    at_hour: int = 9
    at_minute: int = 0
    run_at: str = ""  # ISO timestamp for kind == "once"
    loop_count: int = 1
    speed: float = 1.0
    enabled: bool = True
    name: str = ""
    _last_fired: str = ""

    def validate(self) -> None:
        if self.kind not in ("interval", "daily", "once"):
            raise ValueError("Invalid schedule kind")
        if self.kind == "interval" and self.interval_seconds < 1:
            raise ValueError("Interval must be at least 1 second")
        if self.kind == "daily" and not (0 <= self.at_hour < 24 and 0 <= self.at_minute < 60):
            raise ValueError("Invalid daily time")
        if self.speed <= 0:
            raise ValueError("Speed must be positive")
        if self.loop_count < 0:
            raise ValueError("Loop count must be zero or positive")

    @property
    def display_name(self) -> str:
        return self.name or Path(self.macro_path).stem

    def next_run_after(self, reference: datetime) -> datetime | None:
        """Return the next datetime this schedule should fire at, or None."""
        if not self.enabled:
            return None
        if self.kind == "interval":
            last = self._parse(self._last_fired)
            base = last or reference
            nxt = base + timedelta(seconds=self.interval_seconds)
            return nxt if nxt > reference else reference
        if self.kind == "daily":
            candidate = reference.replace(hour=self.at_hour, minute=self.at_minute, second=0, microsecond=0)
            if candidate <= reference or self._fired_today(reference):
                candidate += timedelta(days=1)
            return candidate
        if self.kind == "once":
            target = self._parse(self.run_at)
            if target is None or self._last_fired:
                return None
            return target
        return None

    def is_due(self, now: datetime) -> bool:
        nxt = self.next_run_after(now - timedelta(seconds=1))
        return nxt is not None and nxt <= now

    def mark_fired(self, now: datetime) -> None:
        self._last_fired = now.isoformat()

    def _fired_today(self, reference: datetime) -> bool:
        last = self._parse(self._last_fired)
        return last is not None and last.date() == reference.date()

    @staticmethod
    def _parse(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def to_dict(self) -> dict[str, object]:
        return {
            "macro_path": self.macro_path,
            "kind": self.kind,
            "interval_seconds": self.interval_seconds,
            "at_hour": self.at_hour,
            "at_minute": self.at_minute,
            "run_at": self.run_at,
            "loop_count": self.loop_count,
            "speed": self.speed,
            "enabled": self.enabled,
            "name": self.name,
            "last_fired": self._last_fired,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Schedule":
        schedule = cls(
            macro_path=str(data.get("macro_path", "")),
            kind=str(data.get("kind", "interval")),  # type: ignore[arg-type]
            interval_seconds=int(data.get("interval_seconds", 3600)),
            at_hour=int(data.get("at_hour", 9)),
            at_minute=int(data.get("at_minute", 0)),
            run_at=str(data.get("run_at", "")),
            loop_count=int(data.get("loop_count", 1)),
            speed=float(data.get("speed", 1.0)),
            enabled=bool(data.get("enabled", True)),
            name=str(data.get("name", "")),
        )
        schedule._last_fired = str(data.get("last_fired", ""))
        return schedule


@dataclass(slots=True)
class ScheduleStore:
    schedules: list[Schedule] = field(default_factory=list)
    _path: Path | None = None

    def add(self, schedule: Schedule) -> None:
        schedule.validate()
        self.schedules.append(schedule)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.schedules):
            del self.schedules[index]

    def due(self, now: datetime | None = None) -> list[Schedule]:
        now = now or datetime.now()
        return [s for s in self.schedules if s.is_due(now)]

    def to_dict(self) -> dict[str, object]:
        return {"version": 1, "schedules": [s.to_dict() for s in self.schedules]}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ScheduleStore":
        raw = data.get("schedules", [])
        schedules = [Schedule.from_dict(s) for s in raw if isinstance(s, dict)]
        return cls(schedules=schedules)

    @classmethod
    def load(cls, path: Path | None = None) -> "ScheduleStore":
        path = path or default_schedule_path()
        store = cls() if not path.exists() else cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        store._path = path
        return store

    def save(self, path: Path | None = None) -> None:
        path = path or self._path or default_schedule_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        self._path = path
