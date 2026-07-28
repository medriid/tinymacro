"""Playlists: play several macros back-to-back as one run.

A playlist references macros by file path (so they stay editable independently)
and, at build time, loads and stitches them into a single :class:`Macro` using the
existing composition primitives (:meth:`Macro.then` / :meth:`Macro.chain` /
:meth:`Macro.repeated`). The stitched macro is what the normal player runs, so
looping, speed, notifications and precise timing all apply to the whole playlist
for free.

Playlists are variant-scoped: a ``docked`` playlist chains Studio ``.tmacd``
macros and a classic one chains ``.tmacc`` macros, because the two use different
coordinate systems and must not be mixed. The build takes a ``loader`` callable so
the host can enforce that (e.g. ``Macro.load_for_variant``).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from tinymacro.core.events import DEFAULT_CONFIDENCE, MacroEvent
from tinymacro.core.macro import Macro

FORMAT = "tiny-macro-playlist"
# v2 adds per-item image gates (wait for an image before the macro plays).
FORMAT_VERSION = 2
PLAYLIST_EXTENSION = ".tmplist"
NANOSECONDS_PER_MS = 1_000_000
DEFAULT_GATE_TIMEOUT_MS = 15_000


@dataclass(slots=True)
class PlaylistItem:
    """One entry in a playlist: a macro file, a repeat count, and an optional
    *image gate* — before this macro plays, wait until ``gate_image`` appears on
    screen (up to ``gate_timeout_ms``). Perfect for "only start once the game has
    loaded in" style sequencing.
    """

    path: str
    repeat: int = 1
    gate_image: str = ""                    # base64 PNG; empty = no gate
    gate_confidence: float = DEFAULT_CONFIDENCE
    gate_timeout_ms: int = DEFAULT_GATE_TIMEOUT_MS
    gate_grayscale: bool = True

    @property
    def display_name(self) -> str:
        return Path(self.path).stem

    @property
    def has_gate(self) -> bool:
        return bool(self.gate_image)

    def gate_event(self) -> MacroEvent | None:
        """A wait-for-image step (no click) to prepend before the macro."""
        if not self.gate_image:
            return None
        return MacroEvent.image_click(
            0, self.gate_image,
            confidence=self.gate_confidence or DEFAULT_CONFIDENCE,
            timeout_ms=self.gate_timeout_ms,
            on_missing="continue",  # after the timeout, play anyway
            click_button="none",    # wait for it; don't click
            grayscale=self.gate_grayscale,
            note="playlist gate",
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"path": self.path, "repeat": self.repeat}
        if self.gate_image:
            data["gate_image"] = self.gate_image
            data["gate_confidence"] = self.gate_confidence
            data["gate_timeout_ms"] = self.gate_timeout_ms
            data["gate_grayscale"] = self.gate_grayscale
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaylistItem":
        return cls(
            path=str(data.get("path", "")),
            repeat=max(1, int(data.get("repeat", 1))),
            gate_image=str(data.get("gate_image", "")),
            gate_confidence=float(data.get("gate_confidence", DEFAULT_CONFIDENCE)),
            gate_timeout_ms=int(data.get("gate_timeout_ms", DEFAULT_GATE_TIMEOUT_MS)),
            gate_grayscale=bool(data.get("gate_grayscale", True)),
        )


@dataclass(slots=True)
class Playlist:
    name: str = "Playlist"
    items: list[PlaylistItem] = field(default_factory=list)
    # Silence inserted between consecutive macros (and between repeats of the same
    # macro) so they don't run into each other.
    gap_ms: int = 200
    docked: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # -- editing --------------------------------------------------------------
    def add(self, path: str | Path, repeat: int = 1) -> PlaylistItem:
        item = PlaylistItem(path=str(path), repeat=max(1, int(repeat)))
        self.items.append(item)
        return item

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]

    def move(self, index: int, direction: int) -> int:
        """Move an item up (-1) or down (+1); returns the item's new index."""
        target = index + direction
        if not (0 <= index < len(self.items)) or not (0 <= target < len(self.items)):
            return index
        self.items[index], self.items[target] = self.items[target], self.items[index]
        return target

    def set_repeat(self, index: int, repeat: int) -> None:
        if 0 <= index < len(self.items):
            self.items[index].repeat = max(1, int(repeat))

    def set_gate(self, index: int, image: str, confidence: float | None = None,
                 timeout_ms: int | None = None, grayscale: bool | None = None) -> None:
        if not (0 <= index < len(self.items)):
            return
        item = self.items[index]
        item.gate_image = image
        if confidence is not None:
            item.gate_confidence = confidence
        if timeout_ms is not None:
            item.gate_timeout_ms = timeout_ms
        if grayscale is not None:
            item.gate_grayscale = grayscale

    def clear_gate(self, index: int) -> None:
        if 0 <= index < len(self.items):
            self.items[index].gate_image = ""

    # -- build ----------------------------------------------------------------
    def build(self, loader: Callable[[str], Macro]) -> Macro:
        """Load every item and stitch them into one macro, in order.

        ``loader`` maps a path to a :class:`Macro` (and should reject the wrong
        variant). Each item is repeated in place, then the items are chained, with
        ``gap_ms`` of silence between every macro. Raises ``ValueError`` if the
        playlist is empty.
        """
        if not self.items:
            raise ValueError("Playlist is empty")
        gap_ns = max(0, self.gap_ms) * NANOSECONDS_PER_MS
        parts: list[Macro] = []
        for item in self.items:
            macro = loader(item.path)
            if item.repeat > 1:
                macro = macro.repeated(item.repeat, gap_ns=gap_ns)
            gate = item.gate_event()
            if gate is not None:
                # Wait for the gate image, then play the macro (once, before repeats
                # is already handled above — the gate fires once per item).
                gate_macro = Macro(events=[gate], docked=self.docked)
                macro = gate_macro.then(macro, gap_ns=0)
            parts.append(macro)
        chained = Macro.chain(parts, gap_ns=gap_ns, name=self.name)
        return chained.copy_with(docked=self.docked)

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "version": FORMAT_VERSION,
            "name": self.name,
            "gap_ms": self.gap_ms,
            "docked": self.docked,
            "created_at": self.created_at,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Playlist":
        if data.get("format") != FORMAT:
            raise ValueError("Not a tiny-macro playlist file")
        if int(data.get("version", 0)) > FORMAT_VERSION:
            raise ValueError("Playlist file was created by a newer version")
        raw_items = data.get("items", [])
        items = [PlaylistItem.from_dict(item) for item in raw_items if isinstance(item, dict)]
        return cls(
            name=str(data.get("name", "Playlist")),
            items=items,
            gap_ms=max(0, int(data.get("gap_ms", 200))),
            docked=bool(data.get("docked", False)),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Playlist":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
