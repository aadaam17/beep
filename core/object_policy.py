"""Protocol-level object classification and conflict policy helpers."""

from __future__ import annotations

from typing import Literal

from core.types import BeepObjectRecord

ObjectVisibility = Literal["public", "public_encrypted", "private_encrypted"]

PUBLIC_OBJECT_TYPES = {
    "post",
    "comment",
    "share",
    "quote",
    "profile",
    "key_revocation",
    "tombstone",
    "presence",
    "follow",
}
PUBLIC_ENCRYPTED_OBJECT_TYPES = {"iro"}
PRIVATE_ENCRYPTED_OBJECT_TYPES = {"chat", "dm", "room_message"}

CONFLICT_RULES: dict[str, str] = {
    "profile": "latest-by-author-timestamp-id",
    "follow": "event-log-author-target-timestamp-id",
    "presence": "freshest-unexpired-by-author-timestamp-id",
    "room": "creation-object-wins-by-room-id",
    "room_event": "authorized-event-log-room-timestamp-id",
    "iro": "highest-payload-version-then-timestamp-id",
}


def object_visibility(obj: BeepObjectRecord) -> ObjectVisibility:
    """Classify an object for retention and sync policy."""

    obj_type = obj.get("type")
    meta = obj.get("meta", {})
    if not isinstance(meta, dict):
        return "private_encrypted"

    if obj_type in PUBLIC_OBJECT_TYPES:
        return "public"
    if obj_type in PUBLIC_ENCRYPTED_OBJECT_TYPES:
        return "public_encrypted"
    if obj_type in PRIVATE_ENCRYPTED_OBJECT_TYPES:
        return "private_encrypted"
    if obj_type == "room":
        return "private_encrypted" if bool(meta.get("private")) else "public"
    if obj_type == "room_event":
        encrypted = meta.get("encrypted")
        return "private_encrypted" if isinstance(encrypted, dict) else "public"
    return "private_encrypted"


def is_private_or_encrypted(obj: BeepObjectRecord) -> bool:
    """Return whether an object carries private/encrypted network semantics."""

    return object_visibility(obj) in {"public_encrypted", "private_encrypted"}
