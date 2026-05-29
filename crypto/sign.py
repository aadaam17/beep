# crypto/sign.py
"""Signing logic for Beep objects using Ed25519 keys
and deterministic root-seed-derived signing keys."""

from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from crypto.seed import load_or_create_root_seed, derive_key_material, SEED_VERSION

SIGN_DIR = Path.home() / ".beep" / "beep_storage/signing"
SIGN_DIR.mkdir(parents=True, exist_ok=True)


def signing_private_bytes_from_seed(root_seed: bytes) -> bytes:
    return derive_key_material(
        root_seed,
        "signing/ed25519",
        length=32,
        version=SEED_VERSION,
    )


def derive_signing_key_from_seed(root_seed: bytes) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    private_bytes = signing_private_bytes_from_seed(root_seed)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    return private_key, private_key.public_key()


def load_or_create_signing_keys(username: str) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Ed25519 keys for signing only."""

    priv_file = SIGN_DIR / f"{username}_ed25519.key"
    root_seed = load_or_create_root_seed(username)
    derived_private_bytes = signing_private_bytes_from_seed(root_seed)

    if priv_file.exists():
        existing = priv_file.read_bytes()
        if existing == derived_private_bytes:
            private_key = Ed25519PrivateKey.from_private_bytes(existing)
        else:
            # Migrate older local key storage to deterministic root-seed-derived signing key.
            priv_file.write_bytes(derived_private_bytes)
            private_key = Ed25519PrivateKey.from_private_bytes(derived_private_bytes)
    else:
        priv_file.write_bytes(derived_private_bytes)
        private_key = Ed25519PrivateKey.from_private_bytes(derived_private_bytes)

    public_key = private_key.public_key()
    return private_key, public_key


def sign_message(private_key: Ed25519PrivateKey, message: str) -> str:
    return private_key.sign(message.encode()).hex()


def verify_message(public_key: Ed25519PublicKey, message: str, signature_hex: str) -> bool:
    try:
        public_key.verify(bytes.fromhex(signature_hex), message.encode())
        return True
    except Exception:
        return False