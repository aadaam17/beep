# crypto/seed.py

import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SEED_DIR = Path.home() / ".beep" / "beep_storage" / "seeds"
SEED_DIR.mkdir(parents=True, exist_ok=True)

SEED_VERSION = 1


def load_or_create_root_seed(username: str) -> bytes:
    """Load an existing root seed or create one for the given user."""

    seed_file = SEED_DIR / f"{username}.seed"
    if seed_file.exists():
        data = seed_file.read_bytes()
        if len(data) != 32:
            raise ValueError("Invalid root seed length")
        return data

    seed = os.urandom(32)
    seed_file.write_bytes(seed)
    return seed


def derive_key_material(
    root_seed: bytes, purpose: str, *, length: int = 32, version: int = SEED_VERSION
) -> bytes:
    """Derive deterministic key material from a root seed."""

    if len(root_seed) != 32:
        raise ValueError("Root seed must be 32 bytes")
    info = f"beep/v{version}/{purpose}".encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=info,
    )
    return hkdf.derive(root_seed)


def seed_fingerprint(root_seed: bytes) -> str:
    """Return a short stable fingerprint for a root seed."""

    digest = hashes.Hash(hashes.SHA256())
    digest.update(root_seed)
    return digest.finalize().hex()[:16]
