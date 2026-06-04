# storage/objects.py
"""Object store helpers and trust-gated persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypeGuard, TypedDict, cast

from core.types import BeepObjectRecord, ObjectSerializable
from core.verify import verify_object
from storage.atomic import atomic_write_json, read_json_with_backup

STORAGE_DIR = Path.home() / ".beep" / "beep_storage"
OBJECTS_DIR = STORAGE_DIR / "objects"
PINS_FILE = STORAGE_DIR / "pins.json"

OBJECTS_DIR.mkdir(parents=True, exist_ok=True)

RetentionReason = Literal[
    "retain",
    "iro",
    "recovery",
    "identity",
    "authored",
    "following",
    "chat_participant",
    "room_participant",
]


class PruneReport(TypedDict):
    """Summary of a prune operation."""

    retained: list[str]
    prunable: list[str]
    pruned: list[str]
    stale_pins_removed: list[str]


class RetentionSummary(TypedDict):
    """Summary of current retention classes."""

    retained: dict[str, int]
    prunable: int
    total: int


def _path(obj_id: str) -> Path:
    """Return the on-disk location for an object ID."""

    return OBJECTS_DIR / f"{obj_id}.json"


def _is_object_serializable(obj: object) -> TypeGuard[ObjectSerializable]:
    """Return whether the value exposes the object serialization protocol."""

    return hasattr(obj, "to_dict")


def _coerce_object_record(
    obj: ObjectSerializable | BeepObjectRecord,
) -> BeepObjectRecord:
    """Normalize an object-like value into a stored payload."""

    if _is_object_serializable(obj):
        return obj.to_dict()
    return cast(BeepObjectRecord, obj)


def save_object(
    obj: ObjectSerializable | BeepObjectRecord,
    *,
    auto_push: bool = True,
) -> bool:
    """Store a verified object once, optionally pushing it to peers."""

    object_record = _coerce_object_record(obj)
    if not verify_object(object_record):
        print("[STORAGE] Rejected untrusted object")
        return False

    object_id = object_record.get("id")
    if not object_id:
        return False

    path = _path(object_id)
    if path.exists():
        return False

    atomic_write_json(path, object_record, indent=2)

    _auto_pin_retained_object(object_record)

    if auto_push:
        from network.sync import push_object_to_peers

        push_object_to_peers(object_record)

    return True


def get_object(obj_id: str) -> BeepObjectRecord | None:
    """Load an object by ID if it exists."""

    path = _path(obj_id)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    if not isinstance(data, dict):
        return None
    return cast(BeepObjectRecord, data)


def list_objects() -> list[str]:
    """List all stored object IDs."""

    return [path.stem for path in OBJECTS_DIR.glob("*.json")]


def load_pins() -> dict[str, str]:
    """Load the object pin registry."""

    data = read_json_with_backup(PINS_FILE, default={})
    if data is None:
        return {}

    if not isinstance(data, dict):
        return {}

    pin_map = cast(dict[str, object], data)
    return {
        obj_id: reason for obj_id, reason in pin_map.items() if isinstance(reason, str)
    }


def _save_pins(pins: dict[str, str]) -> None:
    """Persist the object pin registry."""

    PINS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(PINS_FILE, pins, indent=2)


def pin_object(obj_id: str, reason: str = "retain") -> bool:
    """Pin an object to prevent it from being treated as disposable."""

    if not get_object(obj_id):
        return False

    pins = load_pins()
    if pins.get(obj_id) == reason:
        return True

    pins[obj_id] = reason
    _save_pins(pins)
    return True


def is_pinned(obj_id: str) -> bool:
    """Check whether an object is currently pinned."""

    return obj_id in load_pins()


def pinned_objects(reason: str | None = None) -> list[str]:
    """List pinned object IDs, optionally filtered by pin reason."""

    pins = load_pins()
    if reason is None:
        return sorted(pins.keys())
    return sorted(obj_id for obj_id, why in pins.items() if why == reason)


def query_objects(
    obj_type: str | None = None,
    author: str | None = None,
) -> list[BeepObjectRecord]:
    """Return stored objects filtered by type and/or author."""

    results: list[BeepObjectRecord] = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if obj is None:
            continue
        if obj_type and obj.get("type") != obj_type:
            continue
        if author and obj.get("author") != author:
            continue
        results.append(obj)

    return sorted(results, key=lambda item: item["timestamp"], reverse=True)


def retention_reason(
    obj: BeepObjectRecord,
    *,
    local_pubkeys: set[str] | None = None,
    pins: dict[str, str] | None = None,
) -> RetentionReason | None:
    """Return the canonical retention reason for an object, if any."""

    object_id = obj["id"]
    pin_map = load_pins() if pins is None else pins
    pin_reason = pin_map.get(object_id)
    if pin_reason in {"retain", "iro", "recovery"}:
        return cast(RetentionReason, pin_reason)

    local_keys = _local_pubkeys() if local_pubkeys is None else local_pubkeys
    if obj["author"] not in local_keys:
        followed_pubkeys = _followed_pubkeys(local_keys)
        if obj["author"] in followed_pubkeys and obj["type"] in {
            "post",
            "comment",
            "share",
            "quote",
            "profile",
            "follow",
            "iro",
        }:
            return "following"

        local_usernames = _local_usernames()
        if obj["type"] in {"chat", "dm"} and _chat_related_to_local_users(
            obj, local_usernames
        ):
            return "chat_participant"
        if obj["type"] in {
            "room",
            "room_event",
            "room_message",
        } and _room_related_to_local_users(
            obj,
            local_pubkeys=local_keys,
            local_usernames=local_usernames,
        ):
            return "room_participant"
        return None

    if obj["type"] in {"profile", "iro"}:
        return "identity"
    return "authored"


def prune_objects(*, dry_run: bool = True) -> PruneReport:
    """Prune disposable objects while preserving retained local history."""

    pins = load_pins()
    local_pubkeys = _local_pubkeys()
    retained: list[str] = []
    prunable: list[str] = []
    pruned: list[str] = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if obj is None:
            continue
        reason = retention_reason(obj, local_pubkeys=local_pubkeys, pins=pins)
        if reason is None:
            prunable.append(obj_id)
        else:
            retained.append(obj_id)

    if not dry_run:
        for obj_id in prunable:
            path = _path(obj_id)
            if path.exists():
                path.unlink()
                pruned.append(obj_id)

    stale_pins_removed: list[str] = []
    updated_pins = {
        obj_id: reason for obj_id, reason in pins.items() if _path(obj_id).exists()
    }
    stale_pins_removed = sorted(set(pins) - set(updated_pins))
    if not dry_run and stale_pins_removed:
        _save_pins(updated_pins)

    return {
        "retained": sorted(retained),
        "prunable": sorted(prunable),
        "pruned": sorted(pruned),
        "stale_pins_removed": stale_pins_removed,
    }


def object_retention_reason(obj_id: str) -> RetentionReason | None:
    """Return the retention reason for a stored object ID, if any."""

    obj = get_object(obj_id)
    if obj is None:
        return None
    return retention_reason(obj)


def retained_objects(reason: RetentionReason | None = None) -> list[str]:
    """List stored object IDs currently protected by the retention policy."""

    retained: list[str] = []
    for obj_id in list_objects():
        obj = get_object(obj_id)
        if obj is None:
            continue
        object_reason = retention_reason(obj)
        if object_reason is None:
            continue
        if reason is None or object_reason == reason:
            retained.append(obj_id)
    return sorted(retained)


def retention_summary() -> RetentionSummary:
    """Summarize the current storage retention policy across all objects."""

    retained_counts: dict[str, int] = {}
    prunable = 0
    total = 0

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if obj is None:
            continue
        total += 1
        reason = retention_reason(obj)
        if reason is None:
            prunable += 1
            continue
        retained_counts[reason] = retained_counts.get(reason, 0) + 1

    return {
        "retained": dict(sorted(retained_counts.items())),
        "prunable": prunable,
        "total": total,
    }


def _local_pubkeys() -> set[str]:
    """Return the public keys for local identities."""

    from storage.profile import load_users

    return {user["pubkey"] for user in load_users().values()}


def _local_usernames() -> list[str]:
    """Return local usernames for decryption-aware retention checks."""

    from storage.profile import load_users

    return sorted(load_users().keys())


def _followed_pubkeys(local_pubkeys: set[str]) -> set[str]:
    """Return the union of followed pubkeys for all local identities."""

    from storage.profile import get_effective_following

    followed: set[str] = set()
    for pubkey in local_pubkeys:
        followed.update(get_effective_following(pubkey))
    return followed


def _chat_related_to_local_users(
    obj: BeepObjectRecord,
    local_usernames: list[str],
) -> bool:
    """Return whether a chat object is relevant to a local chat participant."""

    if obj["type"] == "dm":
        return _encrypted_visible_to_local_users(obj, local_usernames)

    chat_id = _string_meta_value(obj, "chat")
    if chat_id is None:
        return False

    for existing in query_objects(obj_type="dm"):
        if _string_meta_value(existing, "chat") != chat_id:
            continue
        if _encrypted_visible_to_local_users(existing, local_usernames):
            return True
    return False


def _room_related_to_local_users(
    obj: BeepObjectRecord,
    *,
    local_pubkeys: set[str],
    local_usernames: list[str],
) -> bool:
    """Return whether a room object is relevant to a local room participant."""

    room_ids = _room_interest_ids(local_pubkeys, local_usernames)
    if obj["type"] == "room":
        room_id = _string_meta_value(obj, "room_id")
        return room_id in room_ids

    room_id = _string_meta_value(obj, "room")
    return room_id in room_ids if room_id is not None else False


def _room_interest_ids(
    local_pubkeys: set[str],
    local_usernames: list[str],
) -> set[str]:
    """Return room IDs that local users own, joined, were invited to, or can read."""

    interest_ids: set[str] = set()

    for obj in query_objects(obj_type="room"):
        if obj["author"] in local_pubkeys:
            room_id = _string_meta_value(obj, "room_id")
            if room_id:
                interest_ids.add(room_id)

    for obj in query_objects(obj_type="room_event"):
        room_id = _string_meta_value(obj, "room")
        if room_id is None:
            continue
        meta = obj.get("meta", {})
        target_pubkey = meta.get("target_pubkey")
        if obj["author"] in local_pubkeys:
            interest_ids.add(room_id)
            continue
        if isinstance(target_pubkey, str) and target_pubkey in local_pubkeys:
            interest_ids.add(room_id)
            continue
        if _encrypted_visible_to_local_users(obj, local_usernames):
            interest_ids.add(room_id)

    for obj in query_objects(obj_type="room_message"):
        room_id = _string_meta_value(obj, "room")
        if room_id is None:
            continue
        if _encrypted_visible_to_local_users(obj, local_usernames):
            interest_ids.add(room_id)

    return interest_ids


def _encrypted_visible_to_local_users(
    obj: BeepObjectRecord,
    local_usernames: list[str],
) -> bool:
    """Return whether an encrypted object can be decrypted by any local user."""

    encrypted = _dict_meta_value(obj, "encrypted")
    if encrypted is None:
        return False

    from storage.crypto import can_decrypt_private_message

    return any(
        can_decrypt_private_message(username, encrypted) for username in local_usernames
    )


def _string_meta_value(obj: BeepObjectRecord, key: str) -> str | None:
    """Extract a string metadata field from a stored object."""

    value = obj["meta"].get(key)
    return value if isinstance(value, str) and value else None


def _dict_meta_value(obj: BeepObjectRecord, key: str) -> dict[str, object] | None:
    """Extract a dictionary metadata field from a stored object."""

    value = obj["meta"].get(key)
    return cast(dict[str, object], value) if isinstance(value, dict) else None


def _auto_pin_retained_object(obj: BeepObjectRecord) -> None:
    """Pin newly stored local objects when the retention policy requires it."""

    reason = retention_reason(obj)
    if reason in {"identity", "authored"}:
        pin_object(obj["id"], reason)
