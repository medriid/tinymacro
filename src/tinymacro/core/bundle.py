"""Portable, self-contained playlist bundles (``.tmbundle``).

A bundle packs a :class:`~tinymacro.core.playlist.Playlist` **together with every
macro it references** (and their embedded gate images) into a single file that
works on any machine and any OS — the playlist's file-path references are rewritten
to in-bundle keys, so nothing points at the author's local disk.

Bundles are gzip-compressed JSON. They can optionally be **encrypted**: password
protected or "open" (no password, but not plaintext). The encryption itself lives
in an optional :mod:`tinymacro.core.securepack` module that ships in official
builds but is not part of the public source tree; when it's absent, bundles are
written/read as plaintext and the encryption options are simply unavailable.
"""
from __future__ import annotations

from collections.abc import Callable
import gzip
import json
from pathlib import Path
from typing import Any

from tinymacro.core.macro import Macro
from tinymacro.core.playlist import Playlist, PlaylistItem

try:  # optional, gitignored, present in official builds
    from tinymacro.core import securepack  # type: ignore
except Exception:  # noqa: BLE001
    securepack = None  # type: ignore

BUNDLE_FORMAT = "tiny-macro-bundle"
BUNDLE_VERSION = 1
BUNDLE_EXTENSION = ".tmbundle"
_GZIP_MAGIC = b"\x1f\x8b"


class BundleError(ValueError):
    """Raised when a bundle is malformed, or encryption is needed but missing."""


def encryption_available() -> bool:
    """True when this build can encrypt/decrypt bundles."""
    return securepack is not None


# -- packing ------------------------------------------------------------------
def _unique_key(existing: dict[str, Any], base: str) -> str:
    key = base or "macro"
    i = 2
    while key in existing:
        key = f"{base}-{i}"
        i += 1
    return key


def build_bundle_dict(playlist: Playlist, loader: Callable[[str], Macro]) -> dict[str, Any]:
    """Load every referenced macro and embed it; rewrite item paths to bundle keys."""
    if not playlist.items:
        raise BundleError("Playlist is empty")
    macros: dict[str, Any] = {}
    new_items: list[PlaylistItem] = []
    for item in playlist.items:
        macro = loader(item.path)
        key = _unique_key(macros, Path(item.path).stem)
        macros[key] = macro.to_dict()
        packed = PlaylistItem.from_dict(item.to_dict())
        packed.path = key  # portable, in-bundle reference
        new_items.append(packed)
    packed_playlist = Playlist(
        name=playlist.name, items=new_items, gap_ms=playlist.gap_ms,
        docked=playlist.docked, created_at=playlist.created_at,
    )
    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "playlist": packed_playlist.to_dict(),
        "macros": macros,
    }


def _dict_to_bytes(data: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(data, separators=(",", ":")).encode("utf-8"), compresslevel=6)


def pack(playlist: Playlist, loader: Callable[[str], Macro], *,
         encrypt: bool = False, password: str | None = None) -> bytes:
    """Serialise a bundle to bytes, optionally encrypted.

    ``encrypt`` with ``password=None`` produces an "open" (no-password) encrypted
    bundle; with a password it is password-protected. Raises :class:`BundleError`
    if encryption is requested but unavailable in this build.
    """
    raw = _dict_to_bytes(build_bundle_dict(playlist, loader))
    if not encrypt:
        return raw
    if securepack is None:
        raise BundleError("This build cannot encrypt bundles (secure module missing).")
    return securepack.encrypt(raw, password)


def save(playlist: Playlist, loader: Callable[[str], Macro], path: str | Path, *,
         encrypt: bool = False, password: str | None = None) -> None:
    Path(path).write_bytes(pack(playlist, loader, encrypt=encrypt, password=password))


# -- unpacking ----------------------------------------------------------------
def is_encrypted(blob: bytes) -> bool:
    return securepack is not None and securepack.is_encrypted(blob)


def needs_password(blob: bytes) -> bool:
    """True if ``blob`` is an encrypted bundle that requires a password to open."""
    return securepack is not None and securepack.is_encrypted(blob) and securepack.needs_password(blob)


def _bytes_to_dict(raw: bytes) -> dict[str, Any]:
    if raw[:2] == _GZIP_MAGIC:
        raw = gzip.decompress(raw)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError("Bundle is corrupt or not a Tiny Macro bundle") from exc


def unpack(blob: bytes, password: str | None = None) -> tuple[Playlist, dict[str, Macro]]:
    """Return (playlist, {key: Macro}) from bundle bytes, decrypting if needed."""
    if securepack is not None and securepack.is_encrypted(blob):
        try:
            blob = securepack.decrypt(blob, password)
        except Exception as exc:  # noqa: BLE001 - wrong password / tamper / missing
            raise BundleError(str(exc) or "Could not decrypt bundle") from exc
    elif securepack is None and blob[:2] != _GZIP_MAGIC:
        raise BundleError("This bundle looks encrypted, but this build can't decrypt it.")
    data = _bytes_to_dict(blob)
    if data.get("format") != BUNDLE_FORMAT:
        raise BundleError("Not a Tiny Macro bundle")
    if int(data.get("version", 0)) > BUNDLE_VERSION:
        raise BundleError("Bundle was created by a newer version of Tiny Macro")
    playlist = Playlist.from_dict(data["playlist"])
    macros = {str(k): Macro.from_dict(v) for k, v in data.get("macros", {}).items()}
    return playlist, macros


def load(path: str | Path, password: str | None = None) -> tuple[Playlist, dict[str, Macro]]:
    return unpack(Path(path).read_bytes(), password)


def macro_loader(macros: dict[str, Macro]) -> Callable[[str], Macro]:
    """A loader for :meth:`Playlist.build` that resolves in-bundle macro keys."""
    def _load(key: str) -> Macro:
        if key not in macros:
            raise BundleError(f"Bundle is missing macro {key!r}")
        return macros[key]
    return _load
