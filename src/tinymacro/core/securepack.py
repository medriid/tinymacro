"""Authenticated encryption for Tiny Macro bundles (``.tmbundle``).

This module is fully open source, and that is fine — its security follows
Kerckhoffs's principle: **everything here is public except the user's password.**

* **password** mode — real cryptographic secrecy. The key is derived from the
  password with **Argon2id** (memory-hard, GPU/ASIC-resistant; scrypt fallback on
  older ``cryptography``) plus a random 32-byte salt, then the payload is sealed
  with **AES-256-GCM** authenticated encryption. A shared bundle is safe even
  against someone holding this entire source tree: the only way in is to guess
  the password, and Argon2id makes each guess very expensive. Use a strong,
  unique password and share it out-of-band.

* **open** mode — *no password*. Honestly: this is **obfuscation and tamper-
  evidence, not confidentiality.** The key comes from a public constant baked
  into the app, so anyone with the app (source or binary) can open it. It stops
  casual reading and silent tampering — nothing more. If you need a shared bundle
  to stay private, give it a password.

Format:  MAGIC(6) | version(1) | mode(1) | salt(32) | nonce(12) | ciphertext(+tag)
The whole header is bound as AES-GCM associated data, so it can't be altered
without failing authentication.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:  # Argon2id (best-practice password KDF) — cryptography >= 44
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    _HAVE_ARGON2 = True
except Exception:  # noqa: BLE001 - fall back to scrypt on older cryptography
    _HAVE_ARGON2 = False

MAGIC = b"TMSEC\x02"
VERSION = 2
MODE_OPEN = 0
MODE_PASSWORD = 1

_SALT = 32
_NONCE = 12
_HEADER = len(MAGIC) + 1 + 1 + _SALT + _NONCE

# A fixed, PUBLIC domain-separation constant folded into every key derivation
# (Argon2's "secret" input). It is not a secret and provides no confidentiality
# on its own — it only namespaces Tiny Macro's key schedule so keys derived here
# don't collide with any other system reusing the same password + Argon2 params.
# Kept stable so bundles written by earlier builds still open.
_DOMAIN = hashlib.sha256(b"tiny-macro/pepper/v2/9f2c8b41d7e04a6f-do-not-rely-on-secrecy").digest()

# Fixed input for "open" (no-password) bundles. Public by design — open bundles
# are obfuscated, never confidential.
_OPEN_SECRET = hashlib.sha256(b"tiny-macro/open-bundle/v2").digest()

# Argon2id cost — strong but still a fraction of a second on a normal machine.
_ARGON_MEM_KIB = 96 * 1024   # 96 MiB
_ARGON_TIME = 4
_ARGON_LANES = 4

# scrypt fallback parameters (only used if Argon2id is unavailable).
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 17, 8, 1


def _derive_key(secret: bytes, salt: bytes) -> bytes:
    if _HAVE_ARGON2:
        return Argon2id(
            salt=salt, length=32, iterations=_ARGON_TIME,
            lanes=_ARGON_LANES, memory_cost=_ARGON_MEM_KIB, secret=_DOMAIN,
        ).derive(secret)
    # Fallback: scrypt over an HMAC(domain, secret) so key derivation still gets
    # the same domain separation the Argon2 path has.
    material = hmac.new(_DOMAIN, secret, hashlib.sha256).digest()
    return hashlib.scrypt(material, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                          dklen=32, maxmem=256 * 1024 * 1024)


def encrypt(data: bytes, password: str | None) -> bytes:
    """Encrypt ``data``; password-protected when ``password`` is given, else open."""
    mode = MODE_PASSWORD if password else MODE_OPEN
    salt = os.urandom(_SALT)
    nonce = os.urandom(_NONCE)
    header = MAGIC + bytes([VERSION, mode]) + salt + nonce
    secret = password.encode("utf-8") if password else _OPEN_SECRET
    key = _derive_key(secret, salt)
    ciphertext = AESGCM(key).encrypt(nonce, data, header)  # header authenticated
    return header + ciphertext


def is_encrypted(blob: bytes) -> bool:
    return blob[: len(MAGIC)] == MAGIC


def needs_password(blob: bytes) -> bool:
    return is_encrypted(blob) and len(blob) > len(MAGIC) + 1 and blob[len(MAGIC) + 1] == MODE_PASSWORD


def decrypt(blob: bytes, password: str | None) -> bytes:
    if not is_encrypted(blob):
        raise ValueError("Not an encrypted bundle")
    if len(blob) < _HEADER:
        raise ValueError("Encrypted bundle is truncated")
    mode = blob[len(MAGIC) + 1]
    if mode == MODE_PASSWORD and not password:
        raise ValueError("This bundle is password-protected — a password is required")
    off = len(MAGIC) + 2
    salt = blob[off : off + _SALT]
    nonce = blob[off + _SALT : off + _SALT + _NONCE]
    header = blob[:_HEADER]
    ciphertext = blob[_HEADER:]
    secret = password.encode("utf-8") if mode == MODE_PASSWORD else _OPEN_SECRET
    key = _derive_key(secret, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, header)
    except Exception as exc:  # InvalidTag etc.
        raise ValueError("Wrong password or the bundle has been tampered with") from exc
