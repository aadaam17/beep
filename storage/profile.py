# storage/profile.py
"""User profile and social graph persistence helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import cast

from core.types import BeepObjectRecord, ObjectMeta, ProfileMeta, UserRecord
from crypto.sign import load_or_create_signing_keys
from storage.crypto import (
    encryption_key_fingerprint,
    exchange_pubkey_to_str,
    load_or_create_exchange_keys,
    pubkey_to_str,
    root_seed_fingerprint,
)
from storage.objects import query_objects

USER_STORAGE_FILE = Path.home() / ".beep" / "beep_users.json"


def _default_user_record(username: str, pubkey: str) -> UserRecord:
    """Build a new local user record with deterministic key metadata."""

    _, exchange_pub = load_or_create_exchange_keys(username)
    enc_pubkey = exchange_pubkey_to_str(exchange_pub)
    return {
        "id": str(uuid.uuid4()),
        "username": username,
        "pubkey": pubkey,
        "enc_pubkey": enc_pubkey,
        "enc_fingerprint": encryption_key_fingerprint(enc_pubkey),
        "key_derivation_version": 1,
        "seed_fingerprint": root_seed_fingerprint(username),
        "signing_scheme": "seed-ed25519-v1",
        "encryption_scheme": "seed-x25519-v1",
        "iro_id": None,
        "password": "",
        "followers": [],
        "following": [],
        "posts": [],
        "shared": [],
    }


def _copy_string_list(source: dict[str, object], user: UserRecord, key: str) -> None:
    """Copy a JSON list into the appropriate typed user field."""

    value = source.get(key)
    if not isinstance(value, list):
        return

    raw_items = cast(list[object], value)
    filtered = [item for item in raw_items if isinstance(item, str)]
    if key == "followers":
        user["followers"] = filtered
    elif key == "following":
        user["following"] = filtered
    elif key == "posts":
        user["posts"] = filtered
    elif key == "shared":
        user["shared"] = filtered


def _optional_string(value: object) -> str | None:
    """Return a non-empty string value or ``None``."""

    return value if isinstance(value, str) and value else None


def _normalize_user_record(username: str, raw_user: object) -> UserRecord:
    """Coerce a loosely typed stored user payload into the canonical shape."""

    if not isinstance(raw_user, dict):
        _, signing_pub = load_or_create_signing_keys(username)
        return _default_user_record(username, pubkey_to_str(signing_pub))

    raw_user_data = cast(dict[str, object], raw_user)

    existing_pubkey = raw_user_data.get("pubkey")
    if isinstance(existing_pubkey, str) and len(existing_pubkey) == 64:
        pubkey = existing_pubkey
    else:
        _, signing_pub = load_or_create_signing_keys(username)
        pubkey = pubkey_to_str(signing_pub)

    user = _default_user_record(username, pubkey)
    user["id"] = str(raw_user_data.get("id") or user["id"])
    user["password"] = str(raw_user_data.get("password") or "")
    user["iro_id"] = _optional_string(raw_user_data.get("iro_id"))

    _copy_string_list(raw_user_data, user, "followers")
    _copy_string_list(raw_user_data, user, "following")
    _copy_string_list(raw_user_data, user, "posts")
    _copy_string_list(raw_user_data, user, "shared")

    username_value = raw_user_data.get("username")
    if isinstance(username_value, str) and username_value:
        user["username"] = username_value

    pubkey_value = raw_user_data.get("pubkey")
    if isinstance(pubkey_value, str) and pubkey_value:
        user["pubkey"] = pubkey_value

    enc_pubkey_value = raw_user_data.get("enc_pubkey")
    if isinstance(enc_pubkey_value, str) and enc_pubkey_value:
        user["enc_pubkey"] = enc_pubkey_value

    enc_fingerprint_value = raw_user_data.get("enc_fingerprint")
    if isinstance(enc_fingerprint_value, str) and enc_fingerprint_value:
        user["enc_fingerprint"] = enc_fingerprint_value

    seed_fingerprint_value = raw_user_data.get("seed_fingerprint")
    if isinstance(seed_fingerprint_value, str) and seed_fingerprint_value:
        user["seed_fingerprint"] = seed_fingerprint_value

    signing_scheme_value = raw_user_data.get("signing_scheme")
    if isinstance(signing_scheme_value, str) and signing_scheme_value:
        user["signing_scheme"] = signing_scheme_value

    encryption_scheme_value = raw_user_data.get("encryption_scheme")
    if isinstance(encryption_scheme_value, str) and encryption_scheme_value:
        user["encryption_scheme"] = encryption_scheme_value

    version = raw_user_data.get("key_derivation_version")
    if isinstance(version, int):
        user["key_derivation_version"] = version

    rsa_pubkey = raw_user_data.get("rsa_pubkey")
    if isinstance(rsa_pubkey, str) and rsa_pubkey:
        user["rsa_pubkey"] = rsa_pubkey
        user["rsa_fingerprint"] = _rsa_fingerprint(rsa_pubkey)

    rsa_fingerprint = raw_user_data.get("rsa_fingerprint")
    if isinstance(rsa_fingerprint, str) and rsa_fingerprint:
        user["rsa_fingerprint"] = rsa_fingerprint

    if not user["enc_pubkey"]:
        _, exchange_pub = load_or_create_exchange_keys(username)
        user["enc_pubkey"] = exchange_pubkey_to_str(exchange_pub)

    if not user["enc_fingerprint"]:
        user["enc_fingerprint"] = encryption_key_fingerprint(user["enc_pubkey"])

    return user


def _normalize_pubkey(users: dict[str, UserRecord]) -> bool:
    """Normalize stored user records in place and report whether anything changed."""

    changed = False
    rewrites: dict[str, str] = {}

    for username, user in users.items():
        existing_pubkey = user["pubkey"]
        if len(existing_pubkey) != 64:
            _, signing_pub = load_or_create_signing_keys(username)
            new_pubkey = pubkey_to_str(signing_pub)
            if existing_pubkey:
                rewrites[existing_pubkey] = new_pubkey
            user["pubkey"] = new_pubkey
            changed = True

        if "rsa_pubkey" in user and "rsa_fingerprint" not in user:
            user["rsa_fingerprint"] = _rsa_fingerprint(user["rsa_pubkey"])
            changed = True

        if not user["seed_fingerprint"]:
            user["seed_fingerprint"] = root_seed_fingerprint(username)
            changed = True

        if not user["enc_pubkey"]:
            _, exchange_pub = load_or_create_exchange_keys(username)
            user["enc_pubkey"] = exchange_pubkey_to_str(exchange_pub)
            changed = True

        expected_fingerprint = encryption_key_fingerprint(user["enc_pubkey"])
        if user["enc_fingerprint"] != expected_fingerprint:
            user["enc_fingerprint"] = expected_fingerprint
            changed = True

    if rewrites:
        for user in users.values():
            user["followers"] = [rewrites.get(pubkey, pubkey) for pubkey in user["followers"]]
            user["following"] = [rewrites.get(pubkey, pubkey) for pubkey in user["following"]]
        changed = True

    return changed


def load_users() -> dict[str, UserRecord]:
    """Load and normalize all persisted users."""

    if not USER_STORAGE_FILE.exists():
        return {}

    raw = json.loads(USER_STORAGE_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    raw_users = cast(dict[str, object], raw)

    users = {
        username: _normalize_user_record(username, raw_user)
        for username, raw_user in raw_users.items()
    }
    if _normalize_pubkey(users):
        save_users(users)
    return users


def save_users(users: dict[str, UserRecord]) -> None:
    """Persist typed user records."""

    USER_STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_STORAGE_FILE.write_text(json.dumps(users, indent=4), encoding="utf-8")


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""

    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_user(username: str, password: str) -> UserRecord:
    """Create a new local user and publish their profile and IRO."""

    users = load_users()
    if username in users:
        raise ValueError(f"Username '{username}' already exists")

    _, pub = load_or_create_signing_keys(username)
    user = _default_user_record(username, pubkey_to_str(pub))
    user["password"] = hash_password(password)
    users[username] = user

    save_users(users)
    _publish_profile(user)
    from storage.iro import publish_local_iro

    publish_local_iro(username)
    return user


def authenticate(username: str, password: str) -> UserRecord:
    """Authenticate a user against the local password store."""

    users = load_users()
    user = users.get(username)
    if user is None:
        raise ValueError(f"Username '{username}' not found")
    if user["password"] != hash_password(password):
        raise ValueError("Incorrect password")
    return user


def get_user_by_pubkey(pubkey: str) -> UserRecord | None:
    """Resolve a user by public key from local or synced profile data."""

    for user in load_users().values():
        if user["pubkey"] == pubkey:
            return user
    return _get_remote_user_by_pubkey(pubkey)


def get_username_by_pubkey(pubkey: str) -> str | None:
    """Resolve a username by public key."""

    user = get_user_by_pubkey(pubkey)
    return user["username"] if user else None


def get_user(username: str) -> UserRecord | None:
    """Get a local user first, then a remote profile-derived user."""

    users = load_users()
    return users.get(username) or _get_remote_user(username)


def update_user(username: str, data: UserRecord | dict[str, object]) -> UserRecord:
    """Update a local user record and republish their profile."""

    users = load_users()
    existing = users.get(username)
    if existing is None:
        raise ValueError(f"Username '{username}' not found")

    merged: dict[str, object] = dict(existing)
    merged.update(data)
    updated = _normalize_user_record(username, merged)
    users[username] = updated
    save_users(users)
    _publish_profile(updated)
    return updated


def follow(user_a: str, user_b: str) -> None:
    """Publish a follow event and update the local compatibility cache."""

    ua = get_user_by_pubkey(user_a)
    ub = get_user_by_pubkey(user_b)
    if ua is None or ub is None:
        raise ValueError("One of the users does not exist")

    _publish_follow_event(user_a, user_b, "follow")
    users = load_users()
    local = users.get(ua["username"])
    if local and user_b not in local["following"]:
        local["following"].append(user_b)
        update_user(ua["username"], local)


def unfollow(user_a_pub: str, user_b_pub: str) -> None:
    """Publish an unfollow event and update the local compatibility cache."""

    ua = get_user_by_pubkey(user_a_pub)
    ub = get_user_by_pubkey(user_b_pub)
    if ua is None or ub is None:
        raise ValueError("One of the users does not exist")

    _publish_follow_event(user_a_pub, user_b_pub, "unfollow")
    users = load_users()
    local = users.get(ua["username"])
    if local and user_b_pub in local["following"]:
        local["following"].remove(user_b_pub)
        update_user(ua["username"], local)


def get_effective_following(pubkey: str) -> set[str]:
    """Compute following state from follow objects."""

    following: set[str] = set()
    objects = sorted(query_objects(obj_type="follow"), key=lambda item: item["timestamp"])
    for obj in objects:
        meta = obj.get("meta", {})
        target = meta.get("target")
        action = meta.get("action")
        if obj.get("author") != pubkey or not isinstance(target, str):
            continue
        if action == "follow":
            following.add(target)
        elif action == "unfollow":
            following.discard(target)
    return following


def get_effective_followers(pubkey: str) -> set[str]:
    """Compute follower state from follow objects."""

    followers: set[str] = set()
    objects = sorted(query_objects(obj_type="follow"), key=lambda item: item["timestamp"])
    for obj in objects:
        meta = obj.get("meta", {})
        target = meta.get("target")
        actor = obj["author"]
        action = meta.get("action")
        if target != pubkey:
            continue
        if action == "follow":
            followers.add(actor)
        elif action == "unfollow":
            followers.discard(actor)
    return followers


def is_following(actor_pubkey: str, target_pubkey: str) -> bool:
    """Return whether the actor currently follows the target."""

    return target_pubkey in get_effective_following(actor_pubkey)


def get_encryption_pubkey(identifier: str) -> str | None:
    """Resolve the published encryption public key for a user."""

    user = get_user(identifier) or get_user_by_pubkey(identifier)
    if user is None:
        return None
    return user.get("enc_pubkey") or user.get("rsa_pubkey")


def get_encryption_fingerprint(identifier: str) -> str | None:
    """Resolve the published encryption key fingerprint for a user."""

    user = get_user(identifier) or get_user_by_pubkey(identifier)
    if user is None:
        return None
    if user.get("enc_fingerprint"):
        return user["enc_fingerprint"]
    if user.get("enc_pubkey"):
        return encryption_key_fingerprint(user["enc_pubkey"])
    return get_rsa_fingerprint(identifier)


def get_rsa_fingerprint(identifier: str) -> str | None:
    """Resolve the legacy RSA fingerprint for a user if it exists."""

    user = get_user(identifier) or get_user_by_pubkey(identifier)
    if user is None:
        return None
    rsa_fingerprint = user.get("rsa_fingerprint")
    if rsa_fingerprint:
        return rsa_fingerprint
    rsa_pubkey = user.get("rsa_pubkey")
    if rsa_pubkey:
        return _rsa_fingerprint(rsa_pubkey)
    return None


def _publish_profile(user: UserRecord) -> None:
    """Publish the current user profile as an immutable object."""

    from core.object import BeepObject
    from storage.objects import save_object

    obj = BeepObject.create_object(
        type_="profile",
        author_pubkey=user["pubkey"],
        content=user["username"],
        meta=cast(ObjectMeta, _profile_meta(user)),
    )
    save_object(obj.to_dict())


def _profile_meta(user: UserRecord) -> ProfileMeta:
    """Build profile object metadata from a typed user record."""

    meta: ProfileMeta = {
        "username": user["username"],
        "enc_pubkey": user["enc_pubkey"],
        "enc_fingerprint": user["enc_fingerprint"],
        "key_derivation_version": user["key_derivation_version"],
        "seed_fingerprint": user["seed_fingerprint"],
        "signing_scheme": user["signing_scheme"],
        "encryption_scheme": user["encryption_scheme"],
    }
    if "rsa_pubkey" in user:
        meta["rsa_pubkey"] = user["rsa_pubkey"]
    if "rsa_fingerprint" in user:
        meta["rsa_fingerprint"] = user["rsa_fingerprint"]
    return meta


def _build_remote_user(obj: BeepObjectRecord) -> UserRecord:
    """Convert a profile object into a derived remote user record."""

    meta = obj.get("meta", {})
    username_value = meta.get("username")
    username = username_value if isinstance(username_value, str) else obj["content"]
    enc_pubkey_value = meta.get("enc_pubkey")
    enc_pubkey = enc_pubkey_value if isinstance(enc_pubkey_value, str) else ""
    enc_fingerprint_value = meta.get("enc_fingerprint")
    enc_fingerprint = (
        enc_fingerprint_value
        if isinstance(enc_fingerprint_value, str)
        else (encryption_key_fingerprint(enc_pubkey) if enc_pubkey else "")
    )

    user = _default_user_record(username, obj["author"])
    user["id"] = obj["id"] or obj["author"]
    user["username"] = username
    user["pubkey"] = obj["author"]
    user["enc_pubkey"] = enc_pubkey
    user["enc_fingerprint"] = enc_fingerprint
    user["password"] = ""

    for key in ("seed_fingerprint", "signing_scheme", "encryption_scheme"):
        value = meta.get(key)
        if key == "seed_fingerprint" and isinstance(value, str) and value:
            user["seed_fingerprint"] = value
        elif key == "signing_scheme" and isinstance(value, str) and value:
            user["signing_scheme"] = value
        elif key == "encryption_scheme" and isinstance(value, str) and value:
            user["encryption_scheme"] = value

    version = meta.get("key_derivation_version")
    if isinstance(version, int):
        user["key_derivation_version"] = version

    rsa_pubkey = meta.get("rsa_pubkey")
    if isinstance(rsa_pubkey, str) and rsa_pubkey:
        user["rsa_pubkey"] = rsa_pubkey
        rsa_fingerprint = meta.get("rsa_fingerprint")
        user["rsa_fingerprint"] = (
            rsa_fingerprint
            if isinstance(rsa_fingerprint, str) and rsa_fingerprint
            else _rsa_fingerprint(rsa_pubkey)
        )

    return user


def _get_remote_user(username: str) -> UserRecord | None:
    """Find a remote user by username from synced profile objects."""

    for obj in query_objects(obj_type="profile"):
        meta_username = obj.get("meta", {}).get("username")
        if meta_username == username or obj.get("content") == username:
            return _build_remote_user(obj)
    return None


def _get_remote_user_by_pubkey(pubkey: str) -> UserRecord | None:
    """Find a remote user by public key from synced profile objects."""

    for obj in query_objects(obj_type="profile"):
        if obj.get("author") == pubkey:
            return _build_remote_user(obj)
    return None


def _publish_follow_event(actor_pubkey: str, target_pubkey: str, action: str) -> None:
    """Publish a follow or unfollow event."""

    from core.object import BeepObject
    from storage.objects import save_object

    actor = get_user_by_pubkey(actor_pubkey)
    if actor is None:
        raise ValueError("Actor does not exist")

    obj = BeepObject.create_object(
        type_="follow",
        author_pubkey=actor_pubkey,
        content=action,
        meta={"action": action, "target": target_pubkey},
    )
    save_object(obj.to_dict())


def _rsa_fingerprint(rsa_pubkey: str) -> str:
    """Create the short legacy RSA fingerprint used in the protocol."""

    return hashlib.sha256(rsa_pubkey.encode("utf-8")).hexdigest()[:16]
