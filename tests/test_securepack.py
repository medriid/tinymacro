"""Security properties of the (now open-source) bundle encryption.

These assert the guarantees the README makes: password bundles are confidential
and authenticated, open bundles round-trip without a password, and any tampering
with the ciphertext or header is detected.
"""
from __future__ import annotations

import pytest

securepack = pytest.importorskip("tinymacro.core.securepack")

PLAINTEXT = b"the quick brown fox jumps over the lazy dog" * 8


def test_password_round_trip():
    blob = securepack.encrypt(PLAINTEXT, "correct horse battery staple")
    assert securepack.is_encrypted(blob)
    assert securepack.needs_password(blob)
    assert securepack.decrypt(blob, "correct horse battery staple") == PLAINTEXT


def test_wrong_password_rejected():
    blob = securepack.encrypt(PLAINTEXT, "s3cret")
    with pytest.raises(ValueError):
        securepack.decrypt(blob, "guess")
    with pytest.raises(ValueError):
        securepack.decrypt(blob, None)  # password mode needs a password


def test_open_mode_needs_no_password():
    blob = securepack.encrypt(PLAINTEXT, None)
    assert securepack.is_encrypted(blob)
    assert not securepack.needs_password(blob)
    assert securepack.decrypt(blob, None) == PLAINTEXT


def test_ciphertext_is_not_plaintext():
    blob = securepack.encrypt(PLAINTEXT, "pw")
    # The payload must not leak the plaintext, and two encryptions of the same
    # data differ (random salt + nonce) — no deterministic fingerprint.
    assert PLAINTEXT not in blob
    other = securepack.encrypt(PLAINTEXT, "pw")
    assert blob != other


def test_tampered_ciphertext_detected():
    blob = bytearray(securepack.encrypt(PLAINTEXT, "pw"))
    blob[-1] ^= 0x01  # flip a bit in the GCM tag / ciphertext
    with pytest.raises(ValueError):
        securepack.decrypt(bytes(blob), "pw")


def test_tampered_header_detected():
    # The header is bound as AES-GCM associated data, so editing the salt fails auth.
    blob = bytearray(securepack.encrypt(PLAINTEXT, "pw"))
    header_salt_index = len(securepack.MAGIC) + 2  # first salt byte
    blob[header_salt_index] ^= 0xFF
    with pytest.raises(ValueError):
        securepack.decrypt(bytes(blob), "pw")


def test_non_bundle_rejected():
    with pytest.raises(ValueError):
        securepack.decrypt(b"not a bundle at all", "pw")
