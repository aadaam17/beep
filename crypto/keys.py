# crypto/keys.py
"""Legacy RSA and deterministic X25519 key helpers."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, x25519
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
)

from crypto.seed import SEED_VERSION, derive_key_material, load_or_create_root_seed
from storage.atomic import atomic_write_bytes

USER_DIR = Path.home() / ".beep" / "beep_storage/users"
USER_DIR.mkdir(parents=True, exist_ok=True)


def load_keys_if_present(
    username: str,
) -> tuple[RSAPrivateKey | None, RSAPublicKey | None]:
    """Load persisted legacy RSA keys when they already exist."""

    priv_file = USER_DIR / f"{username}_rsa_priv.pem"
    pub_file = USER_DIR / f"{username}_rsa_pub.pem"
    if not priv_file.exists() or not pub_file.exists():
        return None, None

    private_key = serialization.load_pem_private_key(
        priv_file.read_bytes(),
        password=None,
    )
    public_key = serialization.load_pem_public_key(pub_file.read_bytes())
    return cast(RSAPrivateKey, private_key), cast(RSAPublicKey, public_key)


def load_or_create_keys(username: str) -> tuple[RSAPrivateKey, RSAPublicKey]:
    """Load legacy RSA keys or create them for compatibility paths."""

    priv_file = USER_DIR / f"{username}_rsa_priv.pem"
    pub_file = USER_DIR / f"{username}_rsa_pub.pem"

    private_key, public_key = load_keys_if_present(username)
    if private_key is not None and public_key is not None:
        return private_key, public_key

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    atomic_write_bytes(
        priv_file,
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    atomic_write_bytes(
        pub_file,
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    return private_key, public_key


def load_or_create_exchange_keys(
    username: str,
) -> tuple[x25519.X25519PrivateKey, x25519.X25519PublicKey]:
    """Derive deterministic X25519 exchange keys from the user's root seed."""

    root_seed = load_or_create_root_seed(username)
    private_bytes = derive_key_material(
        root_seed,
        "encryption/x25519",
        length=32,
        version=SEED_VERSION,
    )
    private_key = x25519.X25519PrivateKey.from_private_bytes(private_bytes)
    return private_key, private_key.public_key()
