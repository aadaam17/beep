# core/signing.py
"""Signing logic for Beep objects using Ed25519 keys."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.hash import HashableObject, canonical_message


def sign_object(obj_fields: HashableObject, private_key: Ed25519PrivateKey) -> str:
    signature = private_key.sign(canonical_message(obj_fields).encode())
    return signature.hex()
