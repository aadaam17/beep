# storage/crypto.py
"""Signing, key serialization, and envelope encryption helpers."""

from __future__ import annotations

import json
import os
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, x25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.types import EncryptedEnvelope, EncryptedKeySlot, RecipientKeyInfo, RecoveryEnvelope
from crypto.keys import (
    load_or_create_exchange_keys as _exchange_keys,
    load_or_create_keys as _rsa_keys,
)
from crypto.seed import (
    SEED_VERSION,
    derive_key_material as _derive_seed_material,
    load_or_create_root_seed as _root_seed,
    seed_fingerprint as _seed_fingerprint,
)
from crypto.sign import sign_message as _sign_message


def load_or_create_keys(username: str):
    """Load or create the legacy RSA keypair for a user."""

    return _rsa_keys(username)


def load_or_create_exchange_keys(username: str, *, epoch: int = 1):
    """Load or create the deterministic X25519 exchange keypair for a user."""

    return _exchange_keys(username, epoch=epoch)


def generate_keys():
    """Generate a temporary legacy RSA keypair."""

    return _rsa_keys("temp_user")


def load_or_create_root_seed(username: str) -> bytes:
    """Load or create the root seed for a user."""

    return _root_seed(username)


def derive_recovery_key(username: str) -> bytes:
    """Derive the recovery key from a user's root seed."""

    return derive_recovery_key_from_seed(_root_seed(username))


def derive_recovery_key_from_seed(root_seed: bytes) -> bytes:
    """Derive the recovery key directly from a seed."""

    return _derive_seed_material(
        root_seed,
        "recovery/aes",
        length=32,
        version=SEED_VERSION,
    )


def root_seed_fingerprint(username: str) -> str:
    """Return the short fingerprint of a user's root seed."""

    return _seed_fingerprint(_root_seed(username))


def sign_message(private_key: Ed25519PrivateKey, message: str) -> str:
    """Sign a message with an Ed25519 private key."""

    return _sign_message(private_key, message)


def pubkey_to_str(pubkey: Ed25519PublicKey | Any) -> str:
    """Serialize a signing or legacy public key to hex text."""

    if isinstance(pubkey, Ed25519PublicKey):
        return pubkey.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    return pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).hex()


def encryption_pubkey_to_str(pubkey: Any) -> str:
    """Serialize a legacy RSA public key to PEM hex."""

    return pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).hex()


def exchange_pubkey_to_str(pubkey: x25519.X25519PublicKey) -> str:
    """Serialize an X25519 public key to raw hex."""

    return pubkey.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def load_encryption_public_key(pubkey_hex: str):
    """Load a legacy RSA public key from serialized PEM hex."""

    return serialization.load_pem_public_key(bytes.fromhex(pubkey_hex))


def load_exchange_public_key(pubkey_hex: str) -> x25519.X25519PublicKey:
    """Load an X25519 public key from raw hex."""

    return x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))


def encryption_key_fingerprint(pubkey_hex: str) -> str:
    """Return a short SHA-256 fingerprint for an encryption public key."""

    digest = hashes.Hash(hashes.SHA256())
    digest.update(pubkey_hex.encode("utf-8"))
    return digest.finalize().hex()[:16]


def encrypt_for_recipients(
    message: str,
    recipient_pubkeys: dict[str, RecipientKeyInfo],
    preferred_scheme: str | None = None,
) -> EncryptedEnvelope:
    """Encrypt a message for recipients using the best available scheme."""

    if not recipient_pubkeys:
        raise ValueError("No recipient keys available")

    scheme = preferred_scheme
    if scheme is None:
        if all(
            info.get("enc_pubkey") and info.get("enc_fingerprint")
            for info in recipient_pubkeys.values()
        ):
            scheme = "x25519-aesgcm-v1"
        else:
            scheme = "rsa-oaep-v1"

    if scheme == "x25519-aesgcm-v1":
        return _encrypt_for_exchange_recipients(message, recipient_pubkeys)
    if scheme == "rsa-oaep-v1":
        return _encrypt_for_rsa_recipients(message, recipient_pubkeys)
    raise ValueError(f"Unsupported encryption scheme: {scheme}")


def _encrypt_for_rsa_recipients(
    message: str,
    recipient_pubkeys: dict[str, RecipientKeyInfo],
) -> EncryptedEnvelope:
    """Encrypt a message using the legacy RSA envelope format."""

    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, message.encode("utf-8"), None)

    encrypted_keys: list[EncryptedKeySlot] = []
    for recipient_info in recipient_pubkeys.values():
        rsa_pubkey = recipient_info.get("rsa_pubkey")
        if not isinstance(rsa_pubkey, str):
            raise ValueError("Missing RSA public key for recipient")
        public_key = load_encryption_public_key(rsa_pubkey)
        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        encrypted_keys.append(
            {
                "key": encrypted_key.hex(),
                "key_id": recipient_info.get("rsa_fingerprint"),
            }
        )

    return {
        "scheme": "rsa-oaep-v1",
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
        "keys": encrypted_keys,
    }


def _encrypt_for_exchange_recipients(
    message: str,
    recipient_pubkeys: dict[str, RecipientKeyInfo],
) -> EncryptedEnvelope:
    """Encrypt a message using deterministic X25519 key agreement."""

    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, message.encode("utf-8"), None)

    encrypted_keys: list[EncryptedKeySlot] = []
    for recipient_info in recipient_pubkeys.values():
        enc_pubkey = recipient_info.get("enc_pubkey")
        enc_fingerprint = recipient_info.get("enc_fingerprint")
        if not isinstance(enc_pubkey, str) or not isinstance(enc_fingerprint, str):
            raise ValueError("Missing deterministic encryption key for recipient")
        public_key = load_exchange_public_key(enc_pubkey)
        ephemeral_private = x25519.X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()
        shared_secret = ephemeral_private.exchange(public_key)
        wrap_key = _derive_wrap_key(shared_secret)
        wrap_nonce = os.urandom(12)
        wrapped_key = AESGCM(wrap_key).encrypt(wrap_nonce, aes_key, None)
        encrypted_keys.append(
            {
                "key": wrapped_key.hex(),
                "key_id": enc_fingerprint,
                "nonce": wrap_nonce.hex(),
                "ephemeral_pubkey": exchange_pubkey_to_str(ephemeral_public),
            }
        )

    return {
        "scheme": "x25519-aesgcm-v1",
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
        "keys": encrypted_keys,
    }


def decrypt_from_envelope(private_key: Any, envelope: dict[str, str]) -> str:
    """Decrypt a legacy RSA message envelope."""

    encrypted_key = bytes.fromhex(envelope["key"])
    aes_key = private_key.decrypt(
        encrypted_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    plaintext = AESGCM(aes_key).decrypt(
        bytes.fromhex(envelope["nonce"]),
        bytes.fromhex(envelope["ciphertext"]),
        None,
    )
    return plaintext.decode("utf-8")


def decrypt_private_message(username: str, encrypted_meta: dict[str, object]) -> str:
    """Decrypt a private message envelope for the local user."""

    scheme = encrypted_meta.get("scheme", "rsa-oaep-v1")
    if scheme == "x25519-aesgcm-v1":
        return _decrypt_exchange_message(username, encrypted_meta)
    if scheme == "rsa-oaep-v1":
        return _decrypt_rsa_message(username, encrypted_meta)
    raise ValueError(f"Unsupported encryption scheme: {scheme}")


def can_decrypt_private_message(username: str, encrypted_meta: dict[str, object]) -> bool:
    """Check whether the local user has a matching decryption slot."""

    return find_local_key_slot(username, encrypted_meta) is not None


def find_local_key_slot(
    username: str,
    encrypted_meta: dict[str, object],
) -> EncryptedKeySlot | None:
    """Find the envelope slot that belongs to the local user."""

    scheme = encrypted_meta.get("scheme", "rsa-oaep-v1")
    if scheme == "x25519-aesgcm-v1":
        for epoch in _local_key_epochs(username):
            _, public_key = load_or_create_exchange_keys(username, epoch=epoch)
            key_id = encryption_key_fingerprint(exchange_pubkey_to_str(public_key))
            slot = find_key_slot(encrypted_meta, [key_id])
            if slot is not None:
                slot["local_epoch"] = epoch
                return slot
    if scheme == "rsa-oaep-v1":
        _, public_key = load_or_create_keys(username)
        key_id = encryption_key_fingerprint(encryption_pubkey_to_str(public_key))
        return find_key_slot(encrypted_meta, [key_id])
    return None


def find_key_slot(
    encrypted_meta: dict[str, object],
    key_ids: str | list[str],
) -> EncryptedKeySlot | None:
    """Find a wrapped key slot matching one of the given key identifiers."""

    normalized_ids = [key_ids] if isinstance(key_ids, str) else key_ids
    slots = encrypted_meta.get("keys", [])
    if isinstance(slots, dict):
        iterable: list[object] = list(slots.values())
    elif isinstance(slots, list):
        iterable = slots
    else:
        iterable = []

    for slot in iterable:
        if isinstance(slot, dict) and slot.get("key_id") in normalized_ids:
            key = slot.get("key")
            key_id = slot.get("key_id")
            if isinstance(key, str) and (isinstance(key_id, str) or key_id is None):
                result: EncryptedKeySlot = {"key": key, "key_id": key_id}
                nonce = slot.get("nonce")
                if isinstance(nonce, str):
                    result["nonce"] = nonce
                ephemeral_pubkey = slot.get("ephemeral_pubkey")
                if isinstance(ephemeral_pubkey, str):
                    result["ephemeral_pubkey"] = ephemeral_pubkey
                return result
    return None


def _decrypt_rsa_message(username: str, encrypted_meta: dict[str, object]) -> str:
    """Decrypt a legacy RSA envelope for the given user."""

    slot = find_local_key_slot(username, encrypted_meta)
    if slot is None:
        raise PermissionError("No RSA decryption slot for this user")

    nonce = encrypted_meta.get("nonce")
    ciphertext = encrypted_meta.get("ciphertext")
    if not isinstance(nonce, str) or not isinstance(ciphertext, str):
        raise ValueError("Invalid RSA envelope")

    private_key, _ = load_or_create_keys(username)
    return decrypt_from_envelope(
        private_key,
        {
            "key": slot["key"],
            "nonce": nonce,
            "ciphertext": ciphertext,
        },
    )


def _decrypt_exchange_message(username: str, encrypted_meta: dict[str, object]) -> str:
    """Decrypt a deterministic X25519 envelope for the given user."""

    slot = find_local_key_slot(username, encrypted_meta)
    if slot is None:
        raise PermissionError("No deterministic decryption slot for this user")
    nonce = encrypted_meta.get("nonce")
    ciphertext = encrypted_meta.get("ciphertext")
    ephemeral_pubkey = slot.get("ephemeral_pubkey")
    wrap_nonce = slot.get("nonce")
    if (
        not isinstance(nonce, str)
        or not isinstance(ciphertext, str)
        or not isinstance(ephemeral_pubkey, str)
        or not isinstance(wrap_nonce, str)
    ):
        raise ValueError("Invalid deterministic envelope")

    local_epoch = slot.get("local_epoch")
    epoch = local_epoch if isinstance(local_epoch, int) else 1
    private_key, _ = load_or_create_exchange_keys(username, epoch=epoch)
    shared_secret = private_key.exchange(load_exchange_public_key(ephemeral_pubkey))
    wrap_key = _derive_wrap_key(shared_secret)
    aes_key = AESGCM(wrap_key).decrypt(
        bytes.fromhex(wrap_nonce),
        bytes.fromhex(slot["key"]),
        None,
    )
    plaintext = AESGCM(aes_key).decrypt(
        bytes.fromhex(nonce),
        bytes.fromhex(ciphertext),
        None,
    )
    return plaintext.decode("utf-8")


def _local_key_epochs(username: str) -> list[int]:
    """Return local encryption epochs to try, newest first."""

    try:
        from storage.profile import load_users

        user = load_users().get(username)
    except Exception:
        user = None
    version = user.get("key_derivation_version") if user else None
    if not isinstance(version, int) or version < 1:
        version = 1
    return list(range(version, 0, -1))


def _derive_wrap_key(shared_secret: bytes) -> bytes:
    """Derive the AES wrapping key from an X25519 shared secret."""

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"beep/v1/x25519-wrap",
    ).derive(shared_secret)


def encrypt_with_recovery_key(
    payload: dict[str, object],
    recovery_key: bytes,
) -> RecoveryEnvelope:
    """Encrypt a recovery payload with the deterministic recovery key."""

    nonce = os.urandom(12)
    ciphertext = AESGCM(recovery_key).encrypt(
        nonce,
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        None,
    )
    return {
        "scheme": "seed-recovery-aes-gcm-v1",
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }


def decrypt_with_recovery_key(
    recovery_key: bytes,
    envelope: dict[str, object],
) -> dict[str, object]:
    """Decrypt a seed-based recovery envelope."""

    nonce = envelope.get("nonce")
    ciphertext = envelope.get("ciphertext")
    if not isinstance(nonce, str) or not isinstance(ciphertext, str):
        raise ValueError("Invalid recovery envelope")

    plaintext = AESGCM(recovery_key).decrypt(
        bytes.fromhex(nonce),
        bytes.fromhex(ciphertext),
        None,
    )
    decoded = json.loads(plaintext.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Invalid recovery payload")
    return {str(key): value for key, value in decoded.items()}
