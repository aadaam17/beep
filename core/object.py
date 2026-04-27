# core/object.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time

from core.hash import compute_object_id
from core.signing import sign_object
from storage.profile import get_user_by_pubkey
from crypto.sign import load_or_create_signing_keys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass
class BeepObject:
    type: str
    author: str  # author_pubkey
    content: str
    timestamp: int = field(default_factory=lambda: int(time.time()))

    meta: Dict[str, Any] = field(default_factory=dict)

    id: Optional[str] = None
    signature: Optional[str] = None

    # --- Canonical serialization ---
    def to_signable_dict(self) -> Dict[str, Any]:
        """
        ONLY fields that are part of hashing/signing.
        """
        return {
            "type": self.type,
            "author": self.author,
            "timestamp": self.timestamp,
            "content": self.content,
            "meta": self.meta,
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Full object (stored form)
        """
        return {
            **self.to_signable_dict(),
            "id": self.id,
            "signature": self.signature,
        }

    # --- ID + signing enforcement ---
    def build_id(self) -> "BeepObject":
        if self.id:
            return self
        self.id = compute_object_id(self.to_signable_dict())
        return self

    def sign(self, private_key: Ed25519PrivateKey) -> "BeepObject":
        if not self.id:
            raise ValueError("Object must be built (id generated) before signing")

        if self.signature:
            raise ValueError("Object is already signed")

        self.signature = sign_object(self.to_signable_dict(), private_key)
        return self

    def finalize(self, private_key: Ed25519PrivateKey) -> "BeepObject":
        """
        Full enforced pipeline:
        build → sign
        """
        return self.build_id().sign(private_key)

    # --- Factory (replaces create_object) ---
    @staticmethod
    def create_object(type_: str, author_pubkey: str, content: str, timestamp: Optional[int] = None, meta=None):
        if meta is None:
            meta = {}

        user = get_user_by_pubkey(author_pubkey)
        if not user:
            raise ValueError("Unknown author")

        priv, _ = load_or_create_signing_keys(user["username"])

        obj = BeepObject(
            type=type_,
            author=author_pubkey,
            content=content,
            timestamp=timestamp or int(time.time()),
            meta=meta,
        )

        obj.finalize(priv)
        return obj

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "BeepObject":
        obj = BeepObject(
            type=data["type"],
            author=data["author"],
            content=data["content"],
            timestamp=data["timestamp"],
            meta=data.get("meta", {}),
            id=data.get("id"),
            signature=data.get("signature"),
        )

        return obj
