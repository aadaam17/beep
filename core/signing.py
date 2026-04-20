from core.hash import canonical_message
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def sign_object(obj_fields: dict, private_key: Ed25519PrivateKey) -> str:
    signature = private_key.sign(canonical_message(obj_fields).encode())
    return signature.hex()

