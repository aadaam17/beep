# storage/backup.py
"""Encrypted backup creation and import helpers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.types import BackupPayload, BeepObjectRecord, EncryptedBackupRecord, IROPayload
from crypto.keys import USER_DIR as RSA_USER_DIR, load_keys_if_present
from crypto.mnemonic import seed_to_mnemonic
from crypto.seed import SEED_DIR, load_or_create_root_seed
from crypto.sign import SIGN_DIR, load_or_create_signing_keys
from storage.crypto import (
    encryption_key_fingerprint,
    encryption_pubkey_to_str,
    exchange_pubkey_to_str,
    load_or_create_exchange_keys,
    pubkey_to_str,
)
from storage.iro import decrypt_iro, get_latest_iro
from storage.objects import get_object, save_object
from storage.profile import USER_STORAGE_FILE, get_user, load_users, save_users

BACKUP_FORMAT_VERSION = 1
PBKDF2_ITERATIONS = 200_000


def create_mnemonic(username: str) -> str:
    """Create a recovery mnemonic from a user's root seed."""

    user = get_user(username)
    if user is None:
        raise ValueError(f"User '{username}' not found")
    return seed_to_mnemonic(load_or_create_root_seed(username))


def create_backup_file(username: str, output_path: str, password: str) -> str:
    """Export an encrypted backup snapshot for a user."""

    user = get_user(username)
    if user is None:
        raise ValueError(f"User '{username}' not found")

    root_seed = load_or_create_root_seed(username)
    signing_private, _ = load_or_create_signing_keys(username)
    rsa_private, rsa_public = load_keys_if_present(username)

    iro_obj = get_latest_iro(username)
    iro_payload = decrypt_iro(username, iro_obj) if iro_obj else None

    object_ids = set(iro_payload["object_ids"] if iro_payload else [])
    iro_id = iro_obj.get("id") if iro_obj else None
    if iro_id:
        object_ids.add(iro_id)

    objects: list[BeepObjectRecord] = []
    for obj_id in sorted(object_ids):
        obj = get_object(obj_id)
        if obj is not None:
            objects.append(obj)

    payload: BackupPayload = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": int(time.time()),
        "username": username,
        "user": user,
        "root_seed": root_seed.hex(),
        "signing_private": signing_private.private_bytes_raw().hex(),
        "iro_id": user.get("iro_id"),
        "iro_payload": iro_payload,
        "objects": objects,
    }
    if rsa_private is not None and rsa_public is not None:
        payload["rsa_private_pem"] = _pem_private_bytes(rsa_private).hex()
        payload["rsa_public_pem"] = _pem_public_bytes(rsa_public).hex()

    encrypted = _encrypt_payload(payload, password)
    backup_path = Path(output_path).expanduser()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")
    return str(backup_path)


def import_backup_file(input_path: str, password: str) -> dict[str, object]:
    """Import an encrypted backup snapshot into local storage."""

    backup_path = Path(input_path).expanduser()
    if not backup_path.exists():
        raise ValueError("Backup file not found")

    encrypted = _load_encrypted_backup(backup_path)
    payload = _decrypt_payload(encrypted, password)
    if payload["format_version"] != BACKUP_FORMAT_VERSION:
        raise ValueError("Unsupported backup format version")

    username = payload["username"]
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    SIGN_DIR.mkdir(parents=True, exist_ok=True)
    RSA_USER_DIR.mkdir(parents=True, exist_ok=True)
    USER_STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)

    (SEED_DIR / f"{username}.seed").write_bytes(bytes.fromhex(payload["root_seed"]))
    (SIGN_DIR / f"{username}_ed25519.key").write_bytes(
        bytes.fromhex(payload["signing_private"])
    )

    rsa_private_pem = payload.get("rsa_private_pem")
    rsa_public_pem = payload.get("rsa_public_pem")
    if isinstance(rsa_private_pem, str) and isinstance(rsa_public_pem, str):
        (RSA_USER_DIR / f"{username}_rsa_priv.pem").write_bytes(
            bytes.fromhex(rsa_private_pem)
        )
        (RSA_USER_DIR / f"{username}_rsa_pub.pem").write_bytes(
            bytes.fromhex(rsa_public_pem)
        )

    _, signing_public = load_or_create_signing_keys(username)
    _, exchange_public = load_or_create_exchange_keys(username)
    _, rsa_public = load_keys_if_present(username)

    user_record = dict(payload["user"])
    user_record["pubkey"] = pubkey_to_str(signing_public)
    user_record["enc_pubkey"] = exchange_pubkey_to_str(exchange_public)
    user_record["enc_fingerprint"] = encryption_key_fingerprint(user_record["enc_pubkey"])
    user_record["encryption_scheme"] = "seed-x25519-v1"
    if rsa_public is not None:
        user_record["rsa_pubkey"] = encryption_pubkey_to_str(rsa_public)
        user_record["rsa_fingerprint"] = _rsa_fingerprint(user_record["rsa_pubkey"])
    else:
        user_record.pop("rsa_pubkey", None)
        user_record.pop("rsa_fingerprint", None)

    users = load_users()
    users[username] = user_record
    save_users(users)

    imported = 0
    for obj in payload["objects"]:
        if save_object(obj, auto_push=False):
            imported += 1

    return {
        "username": username,
        "imported_objects": imported,
        "iro_id": payload["iro_id"],
        "has_iro": payload["iro_payload"] is not None,
    }


def _encrypt_payload(payload: BackupPayload, password: str) -> EncryptedBackupRecord:
    """Encrypt a backup payload for storage."""

    salt = AESGCM.generate_key(bit_length=128)
    key = _derive_password_key(password, salt)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        None,
    )
    return {
        "format": "beep-backup-v1",
        "kdf": {
            "name": "pbkdf2-sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": salt.hex(),
        },
        "cipher": {
            "name": "aes-256-gcm",
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
        },
    }


def _decrypt_payload(encrypted: EncryptedBackupRecord, password: str) -> BackupPayload:
    """Decrypt an encrypted backup record into a typed snapshot payload."""

    if encrypted["format"] != "beep-backup-v1":
        raise ValueError("Unsupported backup file")

    salt = bytes.fromhex(encrypted["kdf"]["salt"])
    key = _derive_password_key(
        password,
        salt,
        iterations=encrypted["kdf"]["iterations"],
    )
    plaintext = AESGCM(key).decrypt(
        bytes.fromhex(encrypted["cipher"]["nonce"]),
        bytes.fromhex(encrypted["cipher"]["ciphertext"]),
        None,
    )
    return _coerce_backup_payload(json.loads(plaintext.decode("utf-8")))


def _load_encrypted_backup(path: Path) -> EncryptedBackupRecord:
    """Load and validate an encrypted backup file record."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Invalid backup file")
    kdf = raw.get("kdf")
    cipher = raw.get("cipher")
    if not isinstance(kdf, dict) or not isinstance(cipher, dict):
        raise ValueError("Invalid backup file")
    return {
        "format": str(raw.get("format", "")),
        "kdf": {
            "name": str(kdf.get("name", "")),
            "iterations": int(kdf.get("iterations", PBKDF2_ITERATIONS)),
            "salt": str(kdf.get("salt", "")),
        },
        "cipher": {
            "name": str(cipher.get("name", "")),
            "nonce": str(cipher.get("nonce", "")),
            "ciphertext": str(cipher.get("ciphertext", "")),
        },
    }


def _coerce_backup_payload(raw_payload: object) -> BackupPayload:
    """Coerce a JSON object into the typed backup payload shape."""

    if not isinstance(raw_payload, dict):
        raise ValueError("Invalid backup payload")

    raw_objects = raw_payload.get("objects")
    objects: list[BeepObjectRecord] = []
    if isinstance(raw_objects, list):
        for item in raw_objects:
            if isinstance(item, dict):
                objects.append(item)

    iro_payload = _coerce_iro_payload(raw_payload.get("iro_payload"))
    user = raw_payload.get("user")
    if not isinstance(user, dict):
        raise ValueError("Invalid backup payload")

    payload: BackupPayload = {
        "format_version": int(raw_payload.get("format_version", 0)),
        "created_at": int(raw_payload.get("created_at", 0)),
        "username": str(raw_payload.get("username", "")),
        "user": user,
        "root_seed": str(raw_payload.get("root_seed", "")),
        "signing_private": str(raw_payload.get("signing_private", "")),
        "iro_id": raw_payload.get("iro_id")
        if isinstance(raw_payload.get("iro_id"), str)
        else None,
        "iro_payload": iro_payload,
        "objects": objects,
    }
    for key in ("rsa_private_pem", "rsa_public_pem"):
        value = raw_payload.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    return payload


def _coerce_iro_payload(raw_payload: object) -> IROPayload | None:
    """Coerce optional backup IRO payload data."""

    if raw_payload is None:
        return None
    if not isinstance(raw_payload, dict):
        raise ValueError("Invalid IRO payload in backup")

    def _string_list(key: str) -> list[str]:
        value = raw_payload.get(key)
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    payload: IROPayload = {
        "version": int(raw_payload.get("version", 1)),
        "username": raw_payload.get("username")
        if isinstance(raw_payload.get("username"), str)
        else None,
        "owner_pubkey": str(raw_payload.get("owner_pubkey", "")),
        "object_ids": _string_list("object_ids"),
        "post_ids": _string_list("post_ids"),
        "chat_ids": _string_list("chat_ids"),
        "room_ids": _string_list("room_ids"),
        "peer_refs": _string_list("peer_refs"),
    }
    for key in ("legacy_rsa_private_pem", "legacy_rsa_public_pem"):
        value = raw_payload.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    return payload


def _derive_password_key(
    password: str,
    salt: bytes,
    *,
    iterations: int = PBKDF2_ITERATIONS,
) -> bytes:
    """Derive the symmetric backup key from a password."""

    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    ).derive(password.encode("utf-8"))


def _pem_private_bytes(private_key: object) -> bytes:
    """Serialize an RSA private key to PEM."""

    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _pem_public_bytes(public_key: object) -> bytes:
    """Serialize an RSA public key to PEM."""

    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _rsa_fingerprint(rsa_pubkey: str) -> str:
    """Create the short legacy RSA fingerprint used in backups."""

    digest = hashes.Hash(hashes.SHA256())
    digest.update(rsa_pubkey.encode("utf-8"))
    return digest.finalize().hex()[:16]
