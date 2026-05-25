# core/schemas.py

from typing import Any
from collections.abc import Mapping

_ENCRYPTED_FIELDS = {"nonce", "ciphertext", "keys"}
_RECOVERY_FIELDS = {"nonce", "ciphertext", "scheme"}
_ROOM_ACTIONS = {
    "invite",
    "join",
    "leave",
    "mod",
    "unmod",
    "mute",
    "unmute",
    "kick",
    "dissolve",
}
_FOLLOW_ACTIONS = {"follow", "unfollow"}


def validate_object_schema(obj: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    obj_type = obj.get("type")
    meta = obj.get("meta", {})

    if not isinstance(meta, dict):
        return ["meta must be an object"]

    if obj_type in {"post"}:
        pass
    elif obj_type == "comment":
        _require_keys(meta, {"parent_id"}, errors, prefix="meta")
        _expect_type(meta, "parent_id", str, errors, prefix="meta")
    elif obj_type == "share":
        _require_keys(meta, {"shared_from"}, errors, prefix="meta")
        _expect_type(meta, "shared_from", str, errors, prefix="meta")
    elif obj_type == "quote":
        _require_keys(meta, {"shared_from"}, errors, prefix="meta")
        _expect_type(meta, "shared_from", str, errors, prefix="meta")
    elif obj_type == "profile":
        _require_keys(meta, {"username"}, errors, prefix="meta")
        _expect_type(meta, "username", str, errors, prefix="meta")
        has_exchange = "enc_pubkey" in meta or "enc_fingerprint" in meta
        has_legacy_rsa = "rsa_pubkey" in meta or "rsa_fingerprint" in meta
        if not has_exchange and not has_legacy_rsa:
            errors.append(
                "meta.enc_pubkey/meta.enc_fingerprint or meta.rsa_pubkey/meta.rsa_fingerprint is required"
            )
        if "enc_pubkey" in meta:
            _expect_type(meta, "enc_pubkey", str, errors, prefix="meta")
        if "enc_fingerprint" in meta:
            _expect_type(meta, "enc_fingerprint", str, errors, prefix="meta")
        if "rsa_pubkey" in meta:
            _expect_type(meta, "rsa_pubkey", str, errors, prefix="meta")
        if "rsa_fingerprint" in meta:
            _expect_type(meta, "rsa_fingerprint", str, errors, prefix="meta")
    elif obj_type == "presence":
        _require_keys(meta, {"username", "endpoint", "reachable_via"}, errors, prefix="meta")
        _expect_type(meta, "username", str, errors, prefix="meta")
        _expect_type(meta, "endpoint", str, errors, prefix="meta")
        _expect_type(meta, "reachable_via", str, errors, prefix="meta")
        if "ttl" in meta:
            _expect_type(meta, "ttl", int, errors, prefix="meta")
        if "relay_hints" in meta and not isinstance(meta["relay_hints"], list):
            errors.append("meta.relay_hints must be list")
    elif obj_type == "iro":
        _require_keys(
            meta,
            {"owner_pubkey", "version", "payload_kind"},
            errors,
            prefix="meta",
        )
        _expect_type(meta, "owner_pubkey", str, errors, prefix="meta")
        _expect_type(meta, "version", int, errors, prefix="meta")
        _expect_type(meta, "payload_kind", str, errors, prefix="meta")
        if meta.get("payload_kind") != "iro_index":
            errors.append("meta.payload_kind must be iro_index")
        has_rsa = "encrypted" in meta
        has_recovery = "recovery_encrypted" in meta
        if not has_rsa and not has_recovery:
            errors.append(
                "meta.encrypted or meta.recovery_encrypted is required"
            )
        if has_rsa:
            _validate_encrypted_meta(
                meta.get("encrypted"), errors, prefix="meta.encrypted"
            )
        if "legacy_encrypted" in meta:
            _validate_encrypted_meta(
                meta.get("legacy_encrypted"),
                errors,
                prefix="meta.legacy_encrypted",
            )
        if has_recovery:
            _validate_recovery_meta(
                meta.get("recovery_encrypted"),
                errors,
                prefix="meta.recovery_encrypted",
            )
    elif obj_type == "follow":
        _require_keys(meta, {"action", "target"}, errors, prefix="meta")
        _expect_type(meta, "action", str, errors, prefix="meta")
        _expect_type(meta, "target", str, errors, prefix="meta")
        if meta.get("action") not in _FOLLOW_ACTIONS:
            errors.append("meta.action must be one of: follow, unfollow")
    elif obj_type == "chat":
        _require_keys(meta, {"chat"}, errors, prefix="meta")
        _expect_type(meta, "chat", str, errors, prefix="meta")
    elif obj_type == "dm":
        _require_keys(meta, {"chat", "encrypted"}, errors, prefix="meta")
        _expect_type(meta, "chat", str, errors, prefix="meta")
        _validate_encrypted_meta(meta.get("encrypted"), errors, prefix="meta.encrypted")
    elif obj_type == "room":
        _require_keys(
            meta,
            {"room_id", "private", "owner_pubkey", "key_epoch"},
            errors,
            prefix="meta",
        )
        _expect_type(meta, "room_id", str, errors, prefix="meta")
        _expect_type(meta, "private", bool, errors, prefix="meta")
        _expect_type(meta, "owner_pubkey", str, errors, prefix="meta")
        _expect_type(meta, "key_epoch", int, errors, prefix="meta")
        if (
            "ttl" in meta
            and meta["ttl"] is not None
            and not isinstance(meta["ttl"], int)
        ):
            errors.append("meta.ttl must be an integer or null")
    elif obj_type == "room_event":
        _require_keys(meta, {"room", "action"}, errors, prefix="meta")
        _expect_type(meta, "room", str, errors, prefix="meta")
        _expect_type(meta, "action", str, errors, prefix="meta")
        if meta.get("action") not in _ROOM_ACTIONS:
            errors.append("meta.action must be a supported room event")
        if meta.get("action") in {
            "invite",
            "join",
            "leave",
            "mod",
            "unmod",
            "mute",
            "unmute",
            "kick",
        }:
            _require_keys(meta, {"target_pubkey"}, errors, prefix="meta")
            _expect_type(meta, "target_pubkey", str, errors, prefix="meta")
        if meta.get("action") == "invite":
            _require_keys(meta, {"target_key_id", "encrypted"}, errors, prefix="meta")
            _expect_type(meta, "target_key_id", str, errors, prefix="meta")
            _validate_encrypted_meta(
                meta.get("encrypted"), errors, prefix="meta.encrypted"
            )
    elif obj_type == "room_message":
        _require_keys(meta, {"room", "encrypted"}, errors, prefix="meta")
        _expect_type(meta, "room", str, errors, prefix="meta")
        _validate_encrypted_meta(meta.get("encrypted"), errors, prefix="meta.encrypted")

    return errors


def _require_keys(
    data: dict[str, Any], keys: set[str], errors: list[str], *, prefix: str
) -> None:
    missing = sorted(keys.difference(data))
    for key in missing:
        errors.append(f"{prefix}.{key} is required")


def _expect_type(
    data: dict[str, Any],
    key: str,
    expected_type: type,
    errors: list[str],
    *,
    prefix: str,
) -> None:
    if key not in data:
        return
    if not isinstance(data[key], expected_type):
        errors.append(f"{prefix}.{key} must be {expected_type.__name__}")


def _validate_encrypted_meta(value: Any, errors: list[str], *, prefix: str) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return

    missing = sorted(_ENCRYPTED_FIELDS.difference(value))
    for field in missing:
        errors.append(f"{prefix}.{field} is required")

    if "nonce" in value and not isinstance(value["nonce"], str):
        errors.append(f"{prefix}.nonce must be str")
    if "ciphertext" in value and not isinstance(value["ciphertext"], str):
        errors.append(f"{prefix}.ciphertext must be str")
    if "keys" in value and not isinstance(value["keys"], (list, dict)):
        errors.append(f"{prefix}.keys must be list or object")
    if "scheme" in value and not isinstance(value["scheme"], str):
        errors.append(f"{prefix}.scheme must be str")


def _validate_recovery_meta(value: Any, errors: list[str], *, prefix: str) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return

    missing = sorted(_RECOVERY_FIELDS.difference(value))
    for field in missing:
        errors.append(f"{prefix}.{field} is required")

    if "scheme" in value and value["scheme"] != "seed-recovery-aes-gcm-v1":
        errors.append(f"{prefix}.scheme must be seed-recovery-aes-gcm-v1")
    if "nonce" in value and not isinstance(value["nonce"], str):
        errors.append(f"{prefix}.nonce must be str")
    if "ciphertext" in value and not isinstance(value["ciphertext"], str):
        errors.append(f"{prefix}.ciphertext must be str")
