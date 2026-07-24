from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable


def default_library_path() -> Path:
    return Path.home() / ".config" / "tiny-macro" / "library.json"


@dataclass(slots=True)
class LibraryEntry:
    path: str
    name: str = ""
    tags: tuple[str, ...] = ()
    favorite: bool = False
    last_run: str = ""
    run_count: int = 0
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def display_name(self) -> str:
        return self.name or Path(self.path).stem

    @property
    def exists(self) -> bool:
        return Path(self.path).exists()

    def matches(self, query: str) -> bool:
        query = query.strip().lower()
        if not query:
            return True
        haystacks = [self.display_name.lower(), self.path.lower(), *[t.lower() for t in self.tags]]
        return any(query in hay for hay in haystacks)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "name": self.name,
            "tags": list(self.tags),
            "favorite": self.favorite,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "LibraryEntry":
        raw_tags = data.get("tags", [])
        tags = tuple(str(t) for t in raw_tags) if isinstance(raw_tags, (list, tuple)) else ()
        return cls(
            path=str(data.get("path", "")),
            name=str(data.get("name", "")),
            tags=tags,
            favorite=bool(data.get("favorite", False)),
            last_run=str(data.get("last_run", "")),
            run_count=int(data.get("run_count", 0)),
            added_at=str(data.get("added_at", datetime.now(timezone.utc).isoformat())),
        )


@dataclass(slots=True)
class MacroLibrary:
    """A small JSON-backed index of macros the user has opened or saved.

    It is deliberately independent of the OS file picker: recents, favorites,
    tags and run stats live here so the manager UI can present a real library.
    """

    entries: list[LibraryEntry] = field(default_factory=list)
    _path: Path | None = None

    def _find(self, path: str) -> LibraryEntry | None:
        normalized = str(Path(path))
        for entry in self.entries:
            if str(Path(entry.path)) == normalized:
                return entry
        return None

    def add(self, path: str | Path, name: str = "", tags: Iterable[str] = ()) -> LibraryEntry:
        existing = self._find(str(path))
        if existing:
            if name:
                existing.name = name
            if tags:
                existing.tags = tuple(dict.fromkeys([*existing.tags, *tags]))
            return existing
        entry = LibraryEntry(path=str(Path(path)), name=name, tags=tuple(tags))
        self.entries.insert(0, entry)
        return entry

    def remove(self, path: str | Path) -> bool:
        entry = self._find(str(path))
        if entry:
            self.entries.remove(entry)
            return True
        return False

    def toggle_favorite(self, path: str | Path) -> bool:
        entry = self._find(str(path))
        if not entry:
            return False
        entry.favorite = not entry.favorite
        return entry.favorite

    def set_tags(self, path: str | Path, tags: Iterable[str]) -> None:
        entry = self._find(str(path))
        if entry:
            entry.tags = tuple(dict.fromkeys(str(t).strip() for t in tags if str(t).strip()))

    def record_run(self, path: str | Path) -> None:
        entry = self._find(str(path)) or self.add(path)
        entry.run_count += 1
        entry.last_run = datetime.now(timezone.utc).isoformat()
        # Keep most-recently-run near the top of the recents view.
        self.entries.remove(entry)
        self.entries.insert(0, entry)

    def search(self, query: str = "", favorites_only: bool = False, tag: str = "") -> list[LibraryEntry]:
        results = self.entries
        if favorites_only:
            results = [e for e in results if e.favorite]
        if tag:
            results = [e for e in results if tag in e.tags]
        return [e for e in results if e.matches(query)]

    def all_tags(self) -> list[str]:
        seen: dict[str, None] = {}
        for entry in self.entries:
            for tag in entry.tags:
                seen[tag] = None
        return sorted(seen)

    def prune_missing(self) -> int:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.exists]
        return before - len(self.entries)

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict[str, object]:
        return {"version": 1, "entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MacroLibrary":
        raw = data.get("entries", [])
        entries = [LibraryEntry.from_dict(e) for e in raw if isinstance(e, dict)]
        return cls(entries=entries)

    @classmethod
    def load(cls, path: Path | None = None) -> "MacroLibrary":
        path = path or default_library_path()
        library = cls() if not path.exists() else cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        library._path = path
        return library

    def save(self, path: Path | None = None) -> None:
        path = path or self._path or default_library_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        self._path = path
