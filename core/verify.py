from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.hash import canonical_message, compute_object_id


def verify_object(obj: dict) -> bool:
    required = {"id", "type", "author", "timestamp", "content", "signature"}
    missing = required.difference(obj)
    if missing:
        print(f"[TRUST] missing field(s): {', '.join(sorted(missing))}")
        return False

    signable = {
        "type": obj["type"],
        "author": obj["author"],
        "timestamp": obj["timestamp"],
        "content": obj["content"],
        "meta": obj.get("meta", {}),
    }

    expected_id = compute_object_id(signable)
    if obj["id"] != expected_id:
        print("[TRUST] invalid object id")
        return False

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(obj["author"]))
        public_key.verify(bytes.fromhex(obj["signature"]), canonical_message(signable).encode())
    except (InvalidSignature, ValueError, TypeError):
        print("[TRUST] invalid signature")
        return False

    return True
