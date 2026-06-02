"""Tests for the signing backends and record verification."""

from __future__ import annotations

import pytest

from ragtrap.records import canonical_message
from ragtrap.signing import Ed25519Signer, HmacSigner, make_signer


def test_ed25519_sign_verify_roundtrip() -> None:
    signer = Ed25519Signer.generate()
    msg = b"provenance-payload"
    sig = signer.sign(msg)
    assert signer.verify(msg, sig) is True


def test_ed25519_rejects_tampered_message() -> None:
    signer = Ed25519Signer.generate()
    sig = signer.sign(b"original")
    assert signer.verify(b"tampered", sig) is False


def test_ed25519_rejects_tampered_signature() -> None:
    signer = Ed25519Signer.generate()
    sig = bytearray(signer.sign(b"original"))
    sig[0] ^= 0xFF
    assert signer.verify(b"original", bytes(sig)) is False


def test_ed25519_other_key_cannot_verify() -> None:
    a = Ed25519Signer.generate()
    b = Ed25519Signer.generate()
    sig = a.sign(b"msg")
    assert b.verify(b"msg", sig) is False
    assert a.public_identity() != b.public_identity()


def test_public_identity_is_not_secret_and_stable() -> None:
    signer = Ed25519Signer.generate()
    assert signer.public_identity().startswith("ed25519:")
    assert signer.public_identity() == signer.public_identity()


def test_hmac_roundtrip_and_rejection() -> None:
    signer = HmacSigner.generate()
    sig = signer.sign(b"x")
    assert signer.verify(b"x", sig) is True
    assert signer.verify(b"y", sig) is False


def test_make_signer_factory() -> None:
    assert make_signer("ed25519").name == "ed25519"
    assert make_signer("hmac").name == "hmac"
    with pytest.raises(ValueError):
        make_signer("rsa")


def test_canonical_message_is_deterministic_and_order_independent() -> None:
    a = canonical_message({"b": 1, "a": 2})
    b = canonical_message({"a": 2, "b": 1})
    assert a == b
