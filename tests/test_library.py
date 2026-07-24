from __future__ import annotations

from tinymacro.core.library import LibraryEntry, MacroLibrary


def test_add_dedupes_and_merges_tags():
    lib = MacroLibrary()
    lib.add("/tmp/a.tmacro", name="A", tags=["x"])
    lib.add("/tmp/a.tmacro", tags=["y"])
    assert len(lib.entries) == 1
    assert set(lib.entries[0].tags) == {"x", "y"}


def test_favorite_and_search():
    lib = MacroLibrary()
    lib.add("/tmp/alpha.tmacro", name="Alpha", tags=["fast"])
    lib.add("/tmp/beta.tmacro", name="Beta")
    lib.toggle_favorite("/tmp/alpha.tmacro")
    favs = lib.search(favorites_only=True)
    assert [e.display_name for e in favs] == ["Alpha"]
    assert [e.display_name for e in lib.search("beta")] == ["Beta"]
    assert lib.search(tag="fast")[0].display_name == "Alpha"


def test_record_run_moves_to_top_and_counts():
    lib = MacroLibrary()
    lib.add("/tmp/a.tmacro", name="A")
    lib.add("/tmp/b.tmacro", name="B")
    lib.record_run("/tmp/a.tmacro")
    assert lib.entries[0].display_name == "A"
    assert lib.entries[0].run_count == 1


def test_round_trip():
    lib = MacroLibrary()
    lib.add("/tmp/a.tmacro", name="A", tags=["t"])
    restored = MacroLibrary.from_dict(lib.to_dict())
    assert restored.entries[0].tags == ("t",)


def test_entry_display_name_falls_back_to_stem():
    entry = LibraryEntry(path="/tmp/thing.tmacro")
    assert entry.display_name == "thing"
