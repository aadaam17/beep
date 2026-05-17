"""Object signature and schema verification."""

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.types import BeepObjectRecord
from core.hash import HashableObject, canonical_message, compute_object_id
from core.schemas import validate_object_schema


def verify_object(obj: BeepObjectRecord) -> bool:
    required = {"id", "type", "author", "timestamp", "content", "signature"}
    missing = required.difference(obj)

    if missing:
        print(f"[TRUST] missing field(s): {', '.join(sorted(missing))}")
        return False

    schema_errors = validate_object_schema(obj)

    if schema_errors:
        print(f"[TRUST] schema error: {schema_errors[0]}")
        return False

    signable: HashableObject = {
        "type": obj["type"],
        "author": obj["author"],
        "timestamp": obj["timestamp"],
        "content": obj["content"],
        "meta": obj["meta"],
    }

    expected_id = compute_object_id(signable)

    if obj["id"] != expected_id:
        print("[TRUST] invalid object id")
        return False

    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(obj["author"])
        )

        public_key.verify(
            bytes.fromhex(obj["signature"]),
            canonical_message(signable).encode(),
        )

    except (InvalidSignature, ValueError, TypeError):
        print("[TRUST] invalid signature")
        return False

    return True
