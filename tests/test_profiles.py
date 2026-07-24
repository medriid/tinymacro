from __future__ import annotations

import pytest

from tinymacro.core.profiles import ProfileStore
from tinymacro.core.settings import Settings


def test_default_profile_exists():
    store = ProfileStore()
    assert store.active == "Default"
    assert isinstance(store.current, Settings)


def test_add_switch_and_duplicate():
    store = ProfileStore()
    qa = store.add("QA")
    qa.speed = 2.0
    store.duplicate("QA", "QA Copy")
    assert set(store.names()) == {"Default", "QA", "QA Copy"}
    store.switch("Default")
    assert store.current.speed == 1.0


def test_cannot_remove_last_profile():
    store = ProfileStore(profiles={"Only": Settings()}, active="Only")
    with pytest.raises(ValueError):
        store.remove("Only")


def test_round_trip():
    store = ProfileStore()
    store.add("QA")
    restored = ProfileStore.from_dict(store.to_dict())
    assert set(restored.names()) == {"Default", "QA"}


def test_import_export(tmp_path):
    store = ProfileStore()
    qa = store.add("QA")
    qa.speed = 3.0
    out = tmp_path / "qa.json"
    store.export_profile("QA", out)
    other = ProfileStore()
    name = other.import_profile(out)
    assert other.profiles[name].speed == 3.0
