"""Custom themes: a portable, self-contained look for Tiny Macro.

A :class:`Theme` describes the whole appearance — a background (solid colour, a
still image, or an animated GIF), translucent surfaces, accent/text colours, the
editor's per-kind palette and an optional UI font. Image/animation bytes are
embedded (base64) so a theme is a *single* file with no external paths, which
makes ``.tmactheme`` files trivially shareable and identical across Windows and
Linux.

This module is pure data — no Qt, no image libraries — so it validates and
round-trips in unit tests. Images are only *sniffed* by magic bytes here; actual
decoding/rendering happens in the GUI layer.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re
from typing import Any

FORMAT = "tiny-macro-theme"
FORMAT_VERSION = 1
THEME_EXTENSION = ".tmactheme"

BG_KINDS = ("solid", "image", "animated")
FIT_MODES = ("cover", "contain", "stretch", "center", "tile")

# Keep a shared theme comfortably small and quick to load; guard against a
# pathological embedded asset. Limits are on the *decoded* asset bytes.
MAX_ASSET_BYTES = 24 * 1024 * 1024      # 24 MB per asset
MAX_TOTAL_ASSET_BYTES = 32 * 1024 * 1024  # 32 MB of assets total

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

_DEFAULT_KIND_COLORS = {"key": "#ffffff", "mouse": "#e0913a", "wheel": "#8a7de0", "wait": "#2f9e6f"}


class ThemeError(ValueError):
    """Raised when a theme is structurally invalid or unsafe to load."""


def default_themes_dir() -> Path:
    return Path.home() / ".config" / "tiny-macro" / "themes"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_hex(value: str) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value.strip()))


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else float(value)


def sniff_image(data: bytes) -> str | None:
    """Return 'png' / 'jpeg' / 'gif' for recognised image bytes, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def _luminance(hex_color: str) -> float:
    """Relative luminance (0..1) of a #RGB/#RRGGBB colour for contrast checks."""
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) >= 6:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    else:
        return 0.0

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two hex colours (1..21)."""
    l1, l2 = _luminance(fg), _luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


@dataclass(slots=True)
class Background:
    kind: str = "solid"           # solid | image | animated
    color: str = "#151515"        # used when kind == solid
    asset: str = ""               # key into Theme.assets for image/animated
    fit: str = "cover"            # cover | contain | stretch | center | tile
    scrim: float = 0.0            # 0..1 dark overlay drawn over an image
    fps_cap: int = 30             # animated: cap playback speed

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind, "fit": self.fit, "scrim": round(self.scrim, 3)}
        if self.kind == "solid":
            data["color"] = self.color
        else:
            data["asset"] = self.asset
            if self.kind == "animated":
                data["fps_cap"] = self.fps_cap
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Background":
        return cls(
            kind=str(data.get("kind", "solid")),
            color=str(data.get("color", "#151515")),
            asset=str(data.get("asset", "")),
            fit=str(data.get("fit", "cover")),
            scrim=_clamp01(float(data.get("scrim", 0.0))),
            fps_cap=int(data.get("fps_cap", 30)),
        )


@dataclass(slots=True)
class Theme:
    name: str = "Custom"
    author: str = ""
    version: int = FORMAT_VERSION
    created_at: str = field(default_factory=_now)
    dark: bool = True
    background: Background = field(default_factory=Background)
    # Surfaces (with an opacity so the background shows through).
    panel: str = "#202020"
    elevated: str = "#2a2a2a"
    border: str = "#3a3a3a"
    panel_opacity: float = 1.0
    # Colours.
    text: str = "#f0f0f0"
    muted: str = "#a8a8a8"
    accent: str = "#ffffff"
    accent_text: str = "#151515"
    kind_colors: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_KIND_COLORS))
    font_family: str = ""
    # name -> base64 PNG/JPG/GIF bytes (may include a "thumbnail" preview).
    assets: dict[str, str] = field(default_factory=dict)

    # -- assets ---------------------------------------------------------------
    def asset_bytes(self, key: str) -> bytes | None:
        raw = self.assets.get(key)
        if not raw:
            return None
        try:
            return base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return None

    def set_asset(self, key: str, data: bytes) -> None:
        self.assets[key] = base64.b64encode(data).decode("ascii")

    def background_bytes(self) -> bytes | None:
        return self.asset_bytes(self.background.asset) if self.background.kind != "solid" else None

    # -- validation -----------------------------------------------------------
    def validate(self) -> list[str]:
        """Raise :class:`ThemeError` on hard problems; return soft warnings."""
        warnings: list[str] = []
        for label, value in (
            ("panel", self.panel), ("elevated", self.elevated), ("border", self.border),
            ("text", self.text), ("muted", self.muted),
            ("accent", self.accent), ("accent_text", self.accent_text),
        ):
            if not _is_hex(value):
                raise ThemeError(f"{label} is not a valid hex colour: {value!r}")
        for k, v in self.kind_colors.items():
            if not _is_hex(v):
                raise ThemeError(f"kind colour {k!r} is not a valid hex colour: {v!r}")
        if not (0.0 <= self.panel_opacity <= 1.0):
            raise ThemeError("panel_opacity must be between 0 and 1")

        bg = self.background
        if bg.kind not in BG_KINDS:
            raise ThemeError(f"background kind must be one of {BG_KINDS}")
        if bg.fit not in FIT_MODES:
            raise ThemeError(f"background fit must be one of {FIT_MODES}")
        if not (0.0 <= bg.scrim <= 1.0):
            raise ThemeError("background scrim must be between 0 and 1")
        if bg.kind == "solid":
            if not _is_hex(bg.color):
                raise ThemeError(f"background colour is not a valid hex colour: {bg.color!r}")
        else:
            data = self.asset_bytes(bg.asset)
            if data is None:
                raise ThemeError(f"background references a missing/invalid asset: {bg.asset!r}")
            kind = sniff_image(data)
            if kind is None:
                raise ThemeError("background asset is not a recognised PNG/JPEG/GIF image")
            if bg.kind == "animated" and kind != "gif":
                warnings.append("animated background asset is not a GIF; it will show as a still image")
            if not (1 <= bg.fps_cap <= 60):
                raise ThemeError("animated fps_cap must be between 1 and 60")

        # Asset size discipline.
        total = 0
        for key in self.assets:
            data = self.asset_bytes(key)
            if data is None:
                raise ThemeError(f"asset {key!r} is not valid base64")
            if len(data) > MAX_ASSET_BYTES:
                raise ThemeError(f"asset {key!r} exceeds the {MAX_ASSET_BYTES // (1024*1024)} MB limit")
            total += len(data)
        if total > MAX_TOTAL_ASSET_BYTES:
            raise ThemeError(f"embedded assets exceed the {MAX_TOTAL_ASSET_BYTES // (1024*1024)} MB total limit")

        # Soft legibility warning.
        base_bg = bg.color if bg.kind == "solid" else self.panel
        if contrast_ratio(self.text, base_bg) < 3.0:
            warnings.append("text may be hard to read against the background (low contrast)")
        return warnings

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "version": FORMAT_VERSION,
            "name": self.name,
            "author": self.author,
            "created_at": self.created_at,
            "dark": self.dark,
            "background": self.background.to_dict(),
            "surfaces": {
                "panel": self.panel,
                "elevated": self.elevated,
                "border": self.border,
                "panel_opacity": round(self.panel_opacity, 3),
            },
            "text": self.text,
            "muted": self.muted,
            "accent": self.accent,
            "accent_text": self.accent_text,
            "kind_colors": dict(self.kind_colors),
            "font_family": self.font_family,
            "assets": dict(self.assets),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Theme":
        if data.get("format") != FORMAT:
            raise ThemeError("Not a tiny-macro theme file")
        if int(data.get("version", 0)) > FORMAT_VERSION:
            raise ThemeError("Theme was created by a newer version of Tiny Macro")
        surfaces = data.get("surfaces", {})
        kinds = data.get("kind_colors", {})
        theme = cls(
            name=str(data.get("name", "Custom")),
            author=str(data.get("author", "")),
            created_at=str(data.get("created_at", _now())),
            dark=bool(data.get("dark", True)),
            background=Background.from_dict(data.get("background", {})),
            panel=str(surfaces.get("panel", "#202020")),
            elevated=str(surfaces.get("elevated", "#2a2a2a")),
            border=str(surfaces.get("border", "#3a3a3a")),
            panel_opacity=_clamp01(float(surfaces.get("panel_opacity", 1.0))),
            text=str(data.get("text", "#f0f0f0")),
            muted=str(data.get("muted", "#a8a8a8")),
            accent=str(data.get("accent", "#ffffff")),
            accent_text=str(data.get("accent_text", "#151515")),
            kind_colors={**_DEFAULT_KIND_COLORS, **{str(k): str(v) for k, v in kinds.items()}},
            font_family=str(data.get("font_family", "")),
            assets={str(k): str(v) for k, v in data.get("assets", {}).items()},
        )
        return theme

    def save(self, path: str | Path) -> None:
        """Write a gzip-compressed JSON ``.tmactheme`` (small, self-contained)."""
        payload = json.dumps(self.to_dict(), separators=(",", ":")).encode("utf-8")
        Path(path).write_bytes(gzip.compress(payload, compresslevel=6))

    @classmethod
    def load(cls, path: str | Path) -> "Theme":
        raw = Path(path).read_bytes()
        if raw[:2] == b"\x1f\x8b":  # gzip magic
            raw = gzip.decompress(raw)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ThemeError("Theme file is corrupt or not a tiny-macro theme") from exc
        theme = cls.from_dict(data)
        theme.validate()  # never load an unsafe/invalid theme
        return theme
