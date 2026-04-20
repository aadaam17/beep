# core/hash.py

import json
import hashlib
from typing import Dict, Any

def canonical_message(obj: dict) -> str:
    """
    IMPORTANT: must be deterministic across all nodes
    """

    return json.dumps(
        {
            "type": obj["type"],
            "author": obj["author"],
            "content": obj["content"],
            "timestamp": obj["timestamp"],
            "meta": obj.get("meta", {}),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_object_id(obj: Dict[str, Any]) -> str:
    """
    Generates content-addressed ID using SHA256.
    MUST NOT include signature field.
    """

    # Only stable fields participate in hashing
    core_obj = {
        "type": obj.get("type"),
        "author": obj.get("author"),
        "timestamp": obj.get("timestamp"),
        "content": obj.get("content"),
        "meta": obj.get("meta", {})
    }

    encoded = canonical_message(core_obj).encode()
    return hashlib.sha256(encoded).hexdigest()
