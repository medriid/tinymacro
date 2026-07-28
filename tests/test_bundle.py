from __future__ import annotations

import base64

import pytest

from tinymacro.core import bundle
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.playlist import Playlist, PlaylistItem

_PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)).decode("ascii")


def _macros():
    return {
        "a.tmacc": Macro(events=[MacroEvent(0, "key", "press", key="a")]),
        "b.tmacc": Macro(events=[MacroEvent(0, "key", "press", key="b")]),
    }


# -- image gates --------------------------------------------------------------
def test_gate_round_trip():
    pl = Playlist(items=[PlaylistItem("a.tmacc")])
    pl.set_gate(0, _PNG, confidence=0.9, timeout_ms=8000)
    assert pl.items[0].has_gate
    restored = Playlist.from_dict(pl.to_dict())
    assert restored.items[0].gate_image == _PNG
    assert restored.items[0].gate_confidence == 0.9
    assert restored.items[0].gate_timeout_ms == 8000


def test_build_prepends_gate_step():
    macros = _macros()
    pl = Playlist(items=[PlaylistItem("a.tmacc"), PlaylistItem("b.tmacc")], gap_ms=0)
    pl.set_gate(0, _PNG)  # gate only the first macro
    built = pl.build(lambda p: macros[p])
    events = built.sorted_events()
    # First event is the gate: a no-click wait-for-image step.
    assert events[0].kind == "image"
    assert events[0].click_button == "none"
    assert events[0].note == "playlist gate"
    # The two key presses are still present, in order.
    keys = [e.key for e in events if e.kind == "key"]
    assert keys == ["a", "b"]


# -- bundle (plaintext, always available) -------------------------------------
def test_bundle_round_trip_plaintext(tmp_path):
    macros = _macros()
    pl = Playlist(name="Combo", items=[PlaylistItem("a.tmacc", repeat=2), PlaylistItem("b.tmacc")], gap_ms=100)
    pl.set_gate(1, _PNG)
    path = tmp_path / "combo.tmbundle"
    bundle.save(pl, lambda p: macros[p], path)

    loaded_pl, loaded_macros = bundle.load(path)
    assert loaded_pl.name == "Combo"
    assert len(loaded_pl.items) == 2
    # Item paths were rewritten to in-bundle keys, and the macros travelled along.
    assert set(loaded_macros) == {"a", "b"}
    assert loaded_pl.items[1].has_gate
    # It rebuilds and plays through the bundle's own loader.
    built = loaded_pl.build(bundle.macro_loader(loaded_macros))
    assert len([e for e in built.sorted_events() if e.kind == "key"]) == 3  # a×2 + b


def test_bundle_rejects_foreign(tmp_path):
    import gzip
    import json

    p = tmp_path / "x.tmbundle"
    p.write_bytes(gzip.compress(json.dumps({"format": "nope"}).encode()))
    with pytest.raises(bundle.BundleError):
        bundle.load(p)


# -- encryption (only when the secure module is present in this build) --------
@pytest.mark.skipif(not bundle.encryption_available(), reason="securepack not present")
def test_bundle_password_round_trip(tmp_path):
    macros = _macros()
    pl = Playlist(items=[PlaylistItem("a.tmacc")])
    blob = bundle.pack(pl, lambda p: macros[p], encrypt=True, password="hunter2")
    assert bundle.is_encrypted(blob) and bundle.needs_password(blob)
    # Wrong / missing password fails.
    with pytest.raises(bundle.BundleError):
        bundle.unpack(blob, "wrong")
    with pytest.raises(bundle.BundleError):
        bundle.unpack(blob, None)
    # Correct password works.
    loaded_pl, loaded_macros = bundle.unpack(blob, "hunter2")
    assert set(loaded_macros) == {"a"}


@pytest.mark.skipif(not bundle.encryption_available(), reason="securepack not present")
def test_bundle_open_encrypted_no_password(tmp_path):
    macros = _macros()
    pl = Playlist(items=[PlaylistItem("a.tmacc")])
    blob = bundle.pack(pl, lambda p: macros[p], encrypt=True, password=None)
    assert bundle.is_encrypted(blob) and not bundle.needs_password(blob)
    loaded_pl, loaded_macros = bundle.unpack(blob, None)  # opens without a password
    assert set(loaded_macros) == {"a"}
