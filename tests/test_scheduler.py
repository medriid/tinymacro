from __future__ import annotations

from datetime import datetime

import pytest

from tinymacro.core.scheduler import Schedule, ScheduleStore


def test_interval_next_run():
    s = Schedule(macro_path="/tmp/a.tmacro", kind="interval", interval_seconds=60)
    s.validate()
    now = datetime(2026, 7, 24, 12, 0, 0)
    nxt = s.next_run_after(now)
    assert nxt == datetime(2026, 7, 24, 12, 1, 0)


def test_daily_next_run_is_tomorrow_when_past():
    s = Schedule(macro_path="/tmp/a.tmacro", kind="daily", at_hour=9, at_minute=0)
    now = datetime(2026, 7, 24, 12, 0, 0)
    assert s.next_run_after(now) == datetime(2026, 7, 25, 9, 0, 0)


def test_is_due_and_mark_fired():
    s = Schedule(macro_path="/tmp/a.tmacro", kind="interval", interval_seconds=1)
    now = datetime(2026, 7, 24, 12, 0, 2)
    assert s.is_due(now)
    s.mark_fired(now)
    assert not s.is_due(now)


def test_once_only_fires_once():
    s = Schedule(macro_path="/tmp/a.tmacro", kind="once", run_at="2026-07-24T12:00:00")
    now = datetime(2026, 7, 24, 12, 0, 1)
    assert s.is_due(now)
    s.mark_fired(now)
    assert s.next_run_after(now) is None


def test_invalid_schedule_rejected():
    with pytest.raises(ValueError):
        Schedule(macro_path="/tmp/a.tmacro", kind="interval", interval_seconds=0).validate()


def test_store_round_trip():
    store = ScheduleStore()
    store.add(Schedule(macro_path="/tmp/a.tmacro", kind="interval", interval_seconds=30))
    restored = ScheduleStore.from_dict(store.to_dict())
    assert len(restored.schedules) == 1
    assert restored.schedules[0].interval_seconds == 30
