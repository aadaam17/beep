# crypto/seed.py
"""Deterministic seed management and key derivation."""

import getpass
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from storage.atomic import atomic_write_bytes, atomic_write_json, read_json_with_backup

SEED_DIR = Path.home() / ".beep" / "beep_storage" / "seeds"
SEED_DIR.mkdir(parents=True, exist_ok=True)

SEED_VERSION = 1
SEED_ENCRYPTION_VERSION = "seed-file-scrypt-aesgcm-v1"
_UNLOCKED_PASSWORDS: dict[str, str] = {}


def unlock_seed_storage(username: str, password: str) -> None:
    """Cache the local password for encrypted seed/key file access."""

    _UNLOCKED_PASSWORDS[username] = password


def store_root_seed(username: str, seed: bytes) -> None:
    """Persist a root seed, encrypted when the identity is unlocked."""

    if len(seed) != 32:
        raise ValueError("Root seed must be 32 bytes")

    encrypted_seed_file = SEED_DIR / f"{username}.seed.enc"
    seed_file = SEED_DIR / f"{username}.seed"
    if username in _UNLOCKED_PASSWORDS:
        _write_encrypted_seed(username, encrypted_seed_file, seed)
        try:
            seed_file.unlink()
        except FileNotFoundError:
            pass
        return
    atomic_write_bytes(seed_file, seed)


def load_or_create_root_seed(username: str) -> bytes:
    """Load an existing root seed or create one for the given user."""

    seed_file = SEED_DIR / f"{username}.seed"
    encrypted_seed_file = SEED_DIR / f"{username}.seed.enc"
    if encrypted_seed_file.exists():
        return _decrypt_seed_file(username, encrypted_seed_file)

    if seed_file.exists():
        data = seed_file.read_bytes()
        if len(data) != 32:
            raise ValueError("Invalid root seed length")
        if username in _UNLOCKED_PASSWORDS:
            _write_encrypted_seed(username, encrypted_seed_file, data)
            seed_file.unlink()
        return data

    seed = os.urandom(32)
    store_root_seed(username, seed)
    return seed


def _decrypt_seed_file(username: str, path: Path) -> bytes:
    password = _UNLOCKED_PASSWORDS.get(username)
    if password is None and sys.stdin.isatty():
        password = getpass.getpass(f"Unlock {username} keys: ")
        if password:
            _UNLOCKED_PASSWORDS[username] = password
    if password is None:
        raise PermissionError("Identity is locked. Log in again to unlock local keys.")
    try:
        payload = read_json_with_backup(path)
        if not isinstance(payload, dict):
            raise ValueError("Invalid encrypted root seed file")
        salt = bytes.fromhex(payload["salt"])
        nonce = bytes.fromhex(payload["nonce"])
        ciphertext = bytes.fromhex(payload["ciphertext"])
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Invalid encrypted root seed file")
    key = _derive_seed_file_key(password, salt)
    seed = AESGCM(key).decrypt(nonce, ciphertext, None)
    if len(seed) != 32:
        raise ValueError("Invalid root seed length")
    return seed


def _write_encrypted_seed(username: str, path: Path, seed: bytes) -> None:
    password = _UNLOCKED_PASSWORDS.get(username)
    if password is None:
        raise PermissionError("Identity is locked. Log in again to unlock local keys.")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_seed_file_key(password, salt)
    payload = {
        "format": SEED_ENCRYPTION_VERSION,
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "ciphertext": AESGCM(key).encrypt(nonce, seed, None).hex(),
    }
    atomic_write_json(path, payload, indent=2)


def _derive_seed_file_key(password: str, salt: bytes) -> bytes:
    return Scrypt(
        salt=salt,
        length=32,
        n=2**14,
        r=8,
        p=1,
    ).derive(password.encode("utf-8"))


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
