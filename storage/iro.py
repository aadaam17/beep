# storage/iro.py

import json
from typing import cast
from cryptography.hazmat.primitives import serialization

from core.object import BeepObject
from core.types import BeepObjectRecord, IROPayload, ObjectMeta
from network.peers import load_peers
from storage.crypto import (
    decrypt_private_message,
    decrypt_with_recovery_key,
    derive_recovery_key,
    derive_recovery_key_from_seed,
    encrypt_with_recovery_key,
    encrypt_for_recipients,
    load_or_create_keys,
)
from crypto.keys import load_keys_if_present
from storage.objects import get_object, pin_object, query_objects, save_object
from storage.profile import (
    get_user,
    get_user_by_pubkey,
    load_users,
    save_users,
)

IRO_VERSION = 1


def publish_local_iro(username: str) -> str | None:
    user = get_user(username)
    if not user:
        raise ValueError(f"User '{username}' not found")

    payload = build_local_iro_payload(user["pubkey"])
    iro_id = publish_iro(user["pubkey"], payload)

    users = load_users()
    if username in users:
        users[username]["iro_id"] = iro_id
        save_users(users)

    return iro_id


def publish_iro(owner_pubkey: str, payload: IROPayload) -> str | None:
    owner = get_user_by_pubkey(owner_pubkey)
    if not owner:
        raise ValueError("Owner does not exist")

    recipient_keys = {
        owner_pubkey: {
            "enc_pubkey": owner.get("enc_pubkey"),
            "enc_fingerprint": owner.get("enc_fingerprint"),
        }
    }
    if owner.get("rsa_pubkey") and owner.get("rsa_fingerprint"):
        recipient_keys[owner_pubkey]["rsa_pubkey"] = owner["rsa_pubkey"]
        recipient_keys[owner_pubkey]["rsa_fingerprint"] = owner["rsa_fingerprint"]
    encrypted = encrypt_for_recipients(
        json.dumps(payload, sort_keys=True), recipient_keys
    )
    legacy_encrypted = None
    if recipient_keys[owner_pubkey].get("rsa_pubkey") and recipient_keys[owner_pubkey].get("rsa_fingerprint"):
        legacy_encrypted = encrypt_for_recipients(
            json.dumps(payload, sort_keys=True),
            recipient_keys,
            preferred_scheme="rsa-oaep-v1",
        )
    recovery_encrypted = encrypt_with_recovery_key(
        payload,
        derive_recovery_key(owner["username"]),
    )
    meta: dict[str, object] = {
        "owner_pubkey": owner_pubkey,
        "version": IRO_VERSION,
        "payload_kind": "iro_index",
        "encrypted": encrypted,
        "recovery_encrypted": recovery_encrypted,
    }
    if legacy_encrypted:
        meta["legacy_encrypted"] = legacy_encrypted

    obj = BeepObject.create_object(
        type_="iro",
        author_pubkey=owner_pubkey,
        content="[encrypted]",
        meta=cast(ObjectMeta, meta),
    )
    save_object(obj.to_dict())
    pin_object(obj.id, "iro")
    return obj.id


def build_local_iro_payload(owner_pubkey: str) -> IROPayload:
    owner = get_user_by_pubkey(owner_pubkey)
    legacy_private, legacy_public = load_keys_if_present(owner["username"])
    owned_objects = [
        obj for obj in query_objects(author=owner_pubkey) if obj.get("type") != "iro"
    ]
    posts = [
        obj["id"]
        for obj in owned_objects
        if obj.get("type") in {"post", "comment", "share", "quote"}
    ]
    chat_ids = sorted(
        {
            obj.get("meta", {}).get("chat")
            for obj in owned_objects
            if obj.get("type") in {"chat", "dm"} and obj.get("meta", {}).get("chat")
        }
    )
    room_ids = sorted(
        {
            obj.get("meta", {}).get("room_id")
            for obj in owned_objects
            if obj.get("type") == "room" and obj.get("meta", {}).get("room_id")
        }
    )

    payload: IROPayload = {
        "version": IRO_VERSION,
        "username": owner["username"] if owner else None,
        "owner_pubkey": owner_pubkey,
        "object_ids": sorted(obj["id"] for obj in owned_objects),
        "post_ids": sorted(posts),
        "chat_ids": chat_ids,
        "room_ids": room_ids,
        "peer_refs": load_peers(),
    }
    if legacy_private and legacy_public:
        payload["legacy_rsa_private_pem"] = legacy_private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()
        payload["legacy_rsa_public_pem"] = legacy_public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).hex()
    return payload


def get_latest_iro(identifier: str) -> BeepObjectRecord | None:
    user = get_user(identifier)
    if user:
        iro_id = user.get("iro_id")
        if iro_id:
            iro_obj = get_object(iro_id)
            if iro_obj:
                return iro_obj
        owner_pubkey = user["pubkey"]
    else:
        owner_pubkey = identifier

    iros = [
        obj
        for obj in query_objects(obj_type="iro")
        if obj.get("author") == owner_pubkey
    ]
    if not iros:
        return None
    return max(iros, key=lambda obj: (obj["timestamp"], obj["id"]))


def decrypt_iro(username: str, iro_obj: BeepObjectRecord | None = None) -> IROPayload | None:
    user = get_user(username)
    if not user:
        raise ValueError(f"User '{username}' not found")

    iro_obj = iro_obj or get_latest_iro(username)
    if not iro_obj:
        return None

    encrypted = iro_obj.get("meta", {}).get("encrypted", {})
    if encrypted:
        try:
            return json.loads(decrypt_private_message(username, encrypted))
        except Exception:
            pass

    legacy_encrypted = iro_obj.get("meta", {}).get("legacy_encrypted", {})
    if legacy_encrypted:
        try:
            return json.loads(decrypt_private_message(username, legacy_encrypted))
        except Exception:
            pass

    recovery_encrypted = iro_obj.get("meta", {}).get("recovery_encrypted")
    if recovery_encrypted:
        return cast(
            IROPayload,
            decrypt_with_recovery_key(
            derive_recovery_key(username),
            recovery_encrypted,
            ),
        )

    raise PermissionError("No decryption slot for this user")


def decrypt_iro_with_seed(root_seed: bytes, iro_obj: BeepObjectRecord | None) -> IROPayload | None:
    if not iro_obj:
        return None
    recovery_encrypted = iro_obj.get("meta", {}).get("recovery_encrypted")
    if not recovery_encrypted:
        raise PermissionError("IRO does not contain a recovery envelope")
    return cast(
        IROPayload,
        decrypt_with_recovery_key(
            derive_recovery_key_from_seed(root_seed),
            recovery_encrypted,
        ),
    )
