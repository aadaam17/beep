# core/object.py
"""Canonical Beep object model and signing pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TypedDict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.hash import compute_object_id
from core.signing import sign_object
from core.types import BeepObjectRecord, ObjectMeta
from crypto.sign import load_or_create_signing_keys


def _default_meta() -> ObjectMeta:
    """Return a typed empty metadata mapping for new objects."""

    return {}


class SignableObjectRecord(TypedDict):
    """Object fields used during hashing and signing before finalization."""

    type: str
    author: str
    content: str
    timestamp: float
    meta: ObjectMeta


@dataclass
class BeepObject:
    """Immutable signed content object."""

    type: str
    author: str
    content: str
    timestamp: float = field(default_factory=time.time)
    meta: ObjectMeta = field(default_factory=_default_meta)
    id: str | None = None
    signature: str | None = None

    def to_signable_dict(self) -> SignableObjectRecord:
        """Serialize the fields that participate in hashing and signing."""

        return {
            "type": self.type,
            "author": self.author,
            "timestamp": self.timestamp,
            "content": self.content,
            "meta": self.meta,
        }

    def to_dict(self) -> BeepObjectRecord:
        """Serialize the full stored form of the object."""

        if self.id is None or self.signature is None:
            raise ValueError("Object must have an id and signature before serialization")

        return {
            "type": self.type,
            "author": self.author,
            "timestamp": self.timestamp,
            "content": self.content,
            "meta": self.meta,
            "id": self.id,
            "signature": self.signature,
        }

    def build_id(self) -> "BeepObject":
        """Compute the content-derived identifier if needed."""

        if self.id:
            return self
        self.id = compute_object_id(self.to_signable_dict())
        return self

    def sign(self, private_key: Ed25519PrivateKey) -> "BeepObject":
        """Sign a previously identified object."""

        if not self.id:
            raise ValueError("Object must be built (id generated) before signing")
        if self.signature:
            raise ValueError("Object is already signed")

        self.signature = sign_object(self.to_signable_dict(), private_key)
        return self

    def finalize(self, private_key: Ed25519PrivateKey) -> "BeepObject":
        """Run the full build-then-sign pipeline."""

        return self.build_id().sign(private_key)

    @staticmethod
    def create_object(
        type_: str,
        author_pubkey: str,
        content: str,
        timestamp: float | None = None,
        meta: ObjectMeta | None = None,
    ) -> "BeepObject":
        """Create, identify, and sign an object for a known author."""

        from storage.profile import get_user_by_pubkey

        object_meta: ObjectMeta = {} if meta is None else meta
        user = get_user_by_pubkey(author_pubkey)
        if not user:
            raise ValueError("Unknown author")

        private_key, _ = load_or_create_signing_keys(user["username"])
        return BeepObject(
            type=type_,
            author=author_pubkey,
            content=content,
            timestamp=time.time() if timestamp is None else timestamp,
            meta=object_meta,
        ).finalize(private_key)

    @staticmethod
    def from_dict(data: BeepObjectRecord) -> "BeepObject":
        """Build an object instance from stored data."""

        return BeepObject(
            type=data["type"],
            author=data["author"],
            content=data["content"],
            timestamp=data["timestamp"],
            meta=data["meta"],
            id=data["id"],
            signature=data["signature"],
        )
