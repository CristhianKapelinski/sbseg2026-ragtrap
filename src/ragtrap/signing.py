"""Signing backends behind a common interface.

Two backends implement :class:`Signer`:

* :class:`Ed25519Signer` -- real public-key signatures (the RAGtrap default). Provenance is
  non-repudiable: anyone holding the public key can verify a record without the private key.
* :class:`HmacSigner` -- a symmetric HMAC-SHA256 stand-in. This reproduces the construction the
  closest prior artifact used in its evaluation ("Ed25519 simulated via HMAC") and exists only
  so the cost and verifiability difference can be measured (experiment E4); it is NOT a
  recommended deployment mode, because the verifier must hold the secret key.

The signed message is a canonical byte string over the provenance tuple (see ``records.py``),
so a signature commits to the source URI, principal, chunk hash, detector verdicts, and
timestamp together.
"""

from __future__ import annotations

import hmac
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)


class Signer(ABC):
    """A signing backend over canonical message bytes."""

    #: short backend identifier recorded in each provenance record
    name: str

    @abstractmethod
    def sign(self, message: bytes) -> bytes:
        """Return the signature over ``message``."""

    @abstractmethod
    def verify(self, message: bytes, signature: bytes) -> bool:
        """Return True iff ``signature`` is valid for ``message``."""

    @abstractmethod
    def public_identity(self) -> str:
        """A non-secret identifier of the verification key, safe to log and publish."""


@dataclass
class Ed25519Signer(Signer):
    """Real Ed25519 signatures (default backend)."""

    name: str = "ed25519"
    _private: Ed25519PrivateKey | None = None

    def __post_init__(self) -> None:
        if self._private is None:
            self._private = Ed25519PrivateKey.generate()

    @classmethod
    def generate(cls) -> Ed25519Signer:
        """Generate a fresh keypair. The private key never leaves the process."""
        return cls(_private=Ed25519PrivateKey.generate())

    @property
    def public_key(self) -> Ed25519PublicKey:
        assert self._private is not None
        return self._private.public_key()

    def public_key_hex(self) -> str:
        """Raw 32-byte public key as hex (safe to log and publish)."""
        raw = self.public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return raw.hex()

    def public_identity(self) -> str:
        return f"ed25519:{self.public_key_hex()}"

    def sign(self, message: bytes) -> bytes:
        assert self._private is not None
        return self._private.sign(message)

    def verify(self, message: bytes, signature: bytes) -> bool:
        try:
            self.public_key.verify(signature, message)
            return True
        except InvalidSignature:
            return False


@dataclass
class HmacSigner(Signer):
    """Symmetric HMAC-SHA256 stand-in (cost-comparison only; see module docstring)."""

    name: str = "hmac"
    _secret: bytes | None = None

    def __post_init__(self) -> None:
        if self._secret is None:
            self._secret = os.urandom(32)

    @classmethod
    def generate(cls) -> HmacSigner:
        return cls(_secret=os.urandom(32))

    def public_identity(self) -> str:
        # An HMAC key is symmetric; there is no public verification key. We expose only a
        # non-reversible tag so logs do not leak the secret while still identifying the key.
        import hashlib

        assert self._secret is not None
        return "hmac:" + hashlib.sha256(self._secret).hexdigest()[:16]

    def sign(self, message: bytes) -> bytes:
        assert self._secret is not None
        return hmac.new(self._secret, message, "sha256").digest()

    def verify(self, message: bytes, signature: bytes) -> bool:
        assert self._secret is not None
        expected = hmac.new(self._secret, message, "sha256").digest()
        return hmac.compare_digest(expected, signature)


def make_signer(name: str) -> Signer:
    """Factory: build a signer by backend name (``ed25519`` or ``hmac``)."""
    key = name.strip().lower()
    if key == "ed25519":
        return Ed25519Signer.generate()
    if key == "hmac":
        return HmacSigner.generate()
    raise ValueError(f"unknown signer backend {name!r}; expected 'ed25519' or 'hmac'")
