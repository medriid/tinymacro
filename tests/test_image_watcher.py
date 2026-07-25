from __future__ import annotations

from tinymacro.core.image_watcher import ImageWatcher
from tinymacro.core.scheduler import Schedule, ScheduleStore


class _FakeLocator:
    def __init__(self) -> None:
        self.present = False

    def locate(self, png, confidence, region=None):
        return object() if self.present else None


def _schedule(loop_count: int = 0) -> Schedule:
    return Schedule(
        macro_path="m.tmacro",
        kind="image",
        image_b64="YWJj",
        confidence=0.8,
        poll_seconds=0.0,
        loop_count=loop_count,
    )


def _watcher(schedule, on_match):
    return ImageWatcher(
        lambda: [schedule],
        lambda: _FakeLocator(),
        on_match=on_match,
        clock=lambda: 0.0,
    )


def test_fires_on_rising_edge_only():
    schedule = _schedule()
    fired: list = []
    watcher = _watcher(schedule, fired.append)
    loc = _FakeLocator()

    loc.present = False
    watcher.poll_once(loc)
    assert fired == []  # absent → no fire

    loc.present = True
    watcher.poll_once(loc)
    assert len(fired) == 1  # rising edge fires

    watcher.poll_once(loc)
    assert len(fired) == 1  # still present but busy → no re-fire


def test_rearm_requires_disappear_then_reappear():
    schedule = _schedule()
    fired: list = []
    watcher = _watcher(schedule, fired.append)
    loc = _FakeLocator()
    loc.present = True
    watcher.poll_once(loc)
    assert len(fired) == 1

    # Playback finished, image still on screen → must not immediately re-fire.
    watcher.rearm(schedule, seen=True)
    watcher.poll_once(loc)
    assert len(fired) == 1

    loc.present = False
    watcher.poll_once(loc)
    loc.present = True
    watcher.poll_once(loc)
    assert len(fired) == 2  # disappear→reappear counts as a new sighting


def test_stops_after_max_fires():
    schedule = _schedule(loop_count=1)

    def host(s: Schedule) -> None:
        s.mark_image_fired()

    watcher = _watcher(schedule, host)
    loc = _FakeLocator()
    loc.present = True
    watcher.poll_once(loc)
    assert schedule.fire_count == 1
    assert schedule.can_fire() is False

    # even after a fresh sighting, a maxed-out trigger never fires again
    watcher.rearm(schedule, seen=False)
    loc.present = False
    watcher.poll_once(loc)
    loc.present = True
    watcher.poll_once(loc)
    assert schedule.fire_count == 1


def test_busy_schedule_is_skipped_when_something_else_runs():
    schedule = _schedule()
    fired: list = []
    watcher = _watcher(schedule, fired.append)
    loc = _FakeLocator()
    loc.present = True
    watcher.poll_once(loc)
    assert len(fired) == 1
    # host could not run it (busy elsewhere) → rearm to retry immediately
    watcher.rearm(schedule, seen=False)
    watcher.poll_once(loc)
    assert len(fired) == 2


def test_image_schedule_round_trip():
    store = ScheduleStore()
    store.add(
        Schedule(
            macro_path="m.tmacro",
            kind="image",
            image_b64="YWJj",
            confidence=0.8,
            poll_seconds=2.0,
            loop_count=3,
        )
    )
    store.schedules[0]._fire_count = 1
    restored = ScheduleStore.from_dict(store.to_dict())
    s = restored.schedules[0]
    assert s.kind == "image"
    assert s.image_b64 == "YWJj"
    assert s.loop_count == 3
    assert s.fire_count == 1
    assert restored.image_triggers() == [s]


def test_v1_schedule_file_loads_under_v2_reader():
    v1 = {
        "version": 1,
        "schedules": [
            {"macro_path": "a.tmacro", "kind": "interval", "interval_seconds": 60, "loop_count": 1}
        ],
    }
    store = ScheduleStore.from_dict(v1)
    assert len(store.schedules) == 1
    assert store.schedules[0].kind == "interval"
    assert store.image_triggers() == []
