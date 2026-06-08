# storage/restore.py
"""Restore and recovery helpers."""

from __future__ import annotations

import uuid

from crypto import seed as crypto_seed
from crypto import sign as crypto_sign
from crypto import keys as crypto_keys
from crypto.mnemonic import mnemonic_to_seed
from network.peers import load_peers
from network.sync import recover_iro_candidates, recover_latest_iro, recover_objects
from storage.backup import import_backup_file
from storage.crypto import (
    encryption_key_fingerprint,
    encryption_pubkey_to_str,
    exchange_pubkey_to_str,
    load_or_create_exchange_keys,
    pubkey_to_str,
)
from storage.iro import decrypt_iro, select_fresh_iro_for_seed
from storage.objects import pinned_objects, query_objects
from storage.profile import _rsa_fingerprint, get_user, hash_password, load_users, save_users
from storage.session import save_session
from storage.atomic import atomic_write_bytes


def restore_from_file(
    path: str,
    password: str,
    *,
    auto_login: bool = True,
) -> dict[str, object]:
    """Restore a local node state from an encrypted backup file."""

    result = import_backup_file(path, password)
    username = _require_string(result, "username")

    if auto_login:
        user = get_user(username)
        if user is None:
            raise ValueError("Restored user record could not be loaded")
        save_session(user["username"], user["pubkey"])
        result["session_restored"] = True
    else:
        result["session_restored"] = False

    try:
        iro_payload = decrypt_iro(username)
    except Exception:
        iro_payload = None

    result["iro_payload"] = iro_payload
    result["recovery_summary"] = _recovery_summary(iro_payload)
    return result


def restore_from_mnemonic(
    mnemonic: str,
    *,
    local_password: str,
    username: str | None = None,
    auto_login: bool = True,
) -> dict[str, object]:
    """Restore identity state from a mnemonic and peer-discovered IRO."""

    root_seed = mnemonic_to_seed(mnemonic)
    _, signing_public = crypto_sign.derive_signing_key_from_seed(root_seed)
    owner_pubkey = pubkey_to_str(signing_public)

    peers = load_peers() or []
    candidates = [
        obj for obj in query_objects(obj_type="iro") if obj.get("author") == owner_pubkey
    ]
    candidates.extend(recover_iro_candidates(owner_pubkey, peers))

    selected = select_fresh_iro_for_seed(root_seed, owner_pubkey, candidates)
    if selected is None:
        raise ValueError(
            "Could not discover a fresh decryptable IRO from configured peers for this mnemonic"
        )
    iro_obj, iro_payload = selected

    restored_username = username or iro_payload["username"]
    if not restored_username:
        raise ValueError(
            "Mnemonic resolved the identity, but the username could not be determined"
        )

    crypto_seed.SEED_DIR.mkdir(parents=True, exist_ok=True)
    crypto_sign.SIGN_DIR.mkdir(parents=True, exist_ok=True)
    crypto_seed.unlock_seed_storage(restored_username, local_password)
    crypto_seed.store_root_seed(restored_username, root_seed)

    legacy_private_hex = iro_payload.get("legacy_rsa_private_pem")
    legacy_public_hex = iro_payload.get("legacy_rsa_public_pem")
    if legacy_private_hex and legacy_public_hex:
        crypto_keys.USER_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(
            crypto_keys.USER_DIR.joinpath(f"{restored_username}_rsa_priv.pem"),
            bytes.fromhex(legacy_private_hex)
        )
        atomic_write_bytes(
            crypto_keys.USER_DIR.joinpath(f"{restored_username}_rsa_pub.pem"),
            bytes.fromhex(legacy_public_hex)
        )

    _, exchange_public = load_or_create_exchange_keys(restored_username)
    enc_pubkey = exchange_pubkey_to_str(exchange_public)
    _, rsa_public = crypto_keys.load_keys_if_present(restored_username)

    users = load_users()
    existing = users.get(restored_username)
    if existing and existing["pubkey"] != owner_pubkey:
        raise ValueError(
            f"Username '{restored_username}' already exists locally with a different identity"
        )

    user_record = {
        "id": existing["id"] if existing is not None else str(uuid.uuid4()),
        "username": restored_username,
        "pubkey": owner_pubkey,
        "enc_pubkey": enc_pubkey,
        "enc_fingerprint": encryption_key_fingerprint(enc_pubkey),
        "key_derivation_version": 1,
        "seed_fingerprint": crypto_seed.seed_fingerprint(root_seed),
        "signing_scheme": "seed-ed25519-v1",
        "encryption_scheme": "seed-x25519-v1",
        "iro_id": iro_obj.get("id"),
        "password": hash_password(local_password),
        "followers": existing["followers"] if existing is not None else [],
        "following": existing["following"] if existing is not None else [],
        "posts": existing["posts"] if existing is not None else [],
        "shared": existing["shared"] if existing is not None else [],
    }
    if rsa_public is not None:
        rsa_pubkey = encryption_pubkey_to_str(rsa_public)
        user_record["rsa_pubkey"] = rsa_pubkey
        user_record["rsa_fingerprint"] = _rsa_fingerprint(rsa_pubkey)
    users[restored_username] = user_record
    save_users(users)

    if auto_login:
        save_session(restored_username, owner_pubkey)

    return {
        "username": restored_username,
        "pubkey": owner_pubkey,
        "iro_payload": iro_payload,
        "iro_id": iro_obj.get("id"),
        "session_restored": auto_login,
        "legacy_messages_unavailable": False,
        "recovery_summary": _recovery_summary(iro_payload),
    }


def recover_missing_from_iro(username: str, *, verbose: bool = True) -> dict[str, object]:
    """Recover missing objects referenced by the user's IRO."""

    user = get_user(username)
    if user is None:
        raise ValueError(f"User '{username}' not found")

    try:
        iro_payload = decrypt_iro(username)
    except Exception:
        iro_payload = None

    peers = list(dict.fromkeys(load_peers() or []))
    if iro_payload is None:
        discovered = recover_latest_iro(user["pubkey"], peers, verbose=verbose)
        if discovered is not None:
            try:
                iro_payload = decrypt_iro(username, discovered)
            except Exception:
                iro_payload = None

    if iro_payload is None:
        return {
            "username": username,
            "imported": 0,
            "missing": [],
            "types": {},
            "peer_count": 0,
            "pinned": 0,
        }

    peers = list(dict.fromkeys([*iro_payload["peer_refs"], *peers]))
    result = recover_objects(
        user["pubkey"],
        iro_payload["object_ids"],
        peers,
        verbose=verbose,
    )
    result["username"] = username
    result["peer_count"] = len(peers)
    result["pinned"] = len(pinned_objects("recovery")) + len(pinned_objects("iro"))
    return result


def _recovery_summary(iro_payload: dict[str, object] | None) -> dict[str, int]:
    """Summarize IRO recovery counts for CLI display."""

    if iro_payload is None:
        return {
            "object_ids": 0,
            "post_ids": 0,
            "chat_ids": 0,
            "room_ids": 0,
            "peer_refs": 0,
        }

    return {
        "object_ids": _list_size(iro_payload.get("object_ids")),
        "post_ids": _list_size(iro_payload.get("post_ids")),
        "chat_ids": _list_size(iro_payload.get("chat_ids")),
        "room_ids": _list_size(iro_payload.get("room_ids")),
        "peer_refs": _list_size(iro_payload.get("peer_refs")),
    }


def _list_size(value: object) -> int:
    """Return the size of a list-like payload field."""

    return len(value) if isinstance(value, list) else 0


def _require_string(data: dict[str, object], key: str) -> str:
    """Require a string value from a generic mapping."""

    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing required field: {key}")
    return value
