# core/hash.py
"""Hashing logic for generating content-addressed object IDs."""

import hashlib
import json
from typing import TypedDict

from core.types import ObjectMeta


class HashableObject(TypedDict):
    """Object fields that participate in canonical hashing."""

    type: str
    author: str
    content: str
    timestamp: float
    meta: ObjectMeta


def canonical_message(obj: HashableObject) -> str:
    """Return the deterministic canonical payload used for hashing."""

    return json.dumps(
        {
            "type": obj["type"],
            "author": obj["author"],
            "content": obj["content"],
            "timestamp": obj["timestamp"],
            "meta": obj["meta"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_object_id(obj: HashableObject) -> str:
    """Generate a content-addressed object ID without using the signature."""

    encoded = canonical_message(obj).encode()
    return hashlib.sha256(encoded).hexdigest()
