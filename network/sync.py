# network/sync.py
"""Peer-to-peer object synchronization utilities."""

from __future__ import annotations

from collections import Counter
from typing import TypeAlias

import requests

from core.object_policy import object_visibility
from core.types import BeepObjectRecord
from core.verify import verify_object
from storage.network_policy import peer_auth_header
from storage.relay import load_network_targets
from storage.objects import get_object, list_objects, pin_object, save_object

TYPE_LABELS = {
    "post": "posts",
    "comment": "comments",
    "share": "shares",
    "quote": "quotes",
    "profile": "profiles",
    "key_revocation": "key revocations",
    "tombstone": "tombstones",
    "iro": "iros",
    "follow": "follows",
    "chat": "chats",
    "dm": "dms",
    "room": "rooms",
    "room_event": "room events",
    "room_message": "room messages",
}

TypeCounter: TypeAlias = Counter[str]
SyncSummary: TypeAlias = dict[str, str | int | bool | TypeCounter]
RecoverySummary: TypeAlias = dict[str, str | int | list[str] | TypeCounter]
INVENTORY_PAGE_LIMIT = 200


def summarize_types(counter: TypeCounter) -> str:
    """Render a human-readable summary of imported object types."""

    if not counter:
        return "nothing new"

    parts: list[str] = []
    for obj_type, count in sorted(counter.items()):
        label = TYPE_LABELS.get(obj_type, obj_type)
        parts.append(f"{count} {label}")
    return ", ".join(parts)


def receive_object(obj: BeepObjectRecord, *, verbose: bool = True) -> bool:
    """Verify and store an incoming object from a peer."""

    if not verify_object(obj):
        if verbose:
            print("[SYNC] rejected untrusted object")
        return False

    stored = save_object(obj, auto_push=False)
    if stored and verbose:
        print(
            f"[SYNC] accepted {obj.get('type', 'object')} {obj.get('id', '')}".strip()
        )
    return stored


def push_object(peer: str, obj: BeepObjectRecord, *, verbose: bool = False) -> bool:
    """Push a single object to a peer."""

    try:
        response = requests.post(
            f"{peer}/object",
            json=obj,
            headers=peer_auth_header(),
            timeout=5,
        )
        return response.status_code in (200, 201, 202)
    except Exception as exc:
        if verbose:
            print(f"[SYNC] push failed to {peer}: {exc}")
        return False


def push_object_to_peers(
    obj: BeepObjectRecord,
    peers: list[str] | None = None,
    *,
    verbose: bool = False,
) -> int:
    """Push a stored object to all known peers."""

    if not _object_is_publicly_replicable(obj):
        if verbose:
            print("[SYNC] skipped private room object")
        return 0

    peer_list = peers if peers is not None else load_network_targets()
    return sum(1 for peer in peer_list if push_object(peer, obj, verbose=verbose))


def push_existing_object(obj_id: str, peers: list[str] | None = None) -> int:
    """Push an already stored object to peers."""

    obj = get_object(obj_id)
    if obj is None:
        return 0
    return push_object_to_peers(obj, peers=peers)


def fetch_object(peer: str, obj_id: str, *, verbose: bool = True) -> BeepObjectRecord | None:
    """Fetch a single object from a peer by ID."""

    try:
        response = requests.get(
            f"{peer}/object/{obj_id}",
            headers=peer_auth_header(),
            timeout=5,
        )
        if response.status_code != 200:
            return None
        payload = _read_json_payload(response)
        if payload is None:
            return None
        if isinstance(payload, dict) and payload.get("error"):
            return None
        return payload if _looks_like_object(payload) else None
    except Exception as exc:
        if verbose:
            print(f"[SYNC] fetch failed from {peer}: {exc}")
        return None


def sync_peer(peer: str, local_ids: set[str], *, verbose: bool = True) -> SyncSummary:
    """Synchronize missing objects from a single peer."""

    summary: SyncSummary = {
        "peer": peer,
        "missing": 0,
        "imported": 0,
        "types": Counter(),
        "failed": False,
    }

    try:
        for remote_ids in iter_inventory_pages(peer):
            missing = [obj_id for obj_id in remote_ids if obj_id not in local_ids]
            summary["missing"] = int(summary["missing"]) + len(missing)

            for obj_id in missing:
                obj = fetch_object(peer, obj_id, verbose=verbose)
                if obj is None:
                    continue

                if receive_object(obj, verbose=verbose):
                    obj_type = obj.get("type", "object")
                    summary["imported"] = int(summary["imported"]) + 1
                    summary["types"][obj_type] += 1
                    local_ids.add(obj_id)
    except Exception as exc:
        if verbose:
            print(f"[SYNC] peer failed {peer}: {exc}")
        summary["failed"] = True

    return summary


def iter_inventory_pages(peer: str, *, limit: int = INVENTORY_PAGE_LIMIT):
    """Yield remote object ID pages, preferring cursor inventory over full scans."""

    cursor: str | None = None
    used_inventory = False
    while True:
        params: dict[str, object] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(
            f"{peer}/inventory",
            params=params,
            headers=peer_auth_header(),
            timeout=5,
        )
        if response.status_code == 404:
            break
        if response.status_code != 200:
            raise RuntimeError(f"inventory failed with HTTP {response.status_code}")
        payload = _read_json_payload(response)
        if not isinstance(payload, dict):
            raise RuntimeError("invalid inventory payload")
        ids = _string_list(payload.get("ids"))
        yield ids
        used_inventory = True
        next_cursor = payload.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            return
        cursor = next_cursor

    if not used_inventory:
        response = requests.get(
            f"{peer}/objects",
            headers=peer_auth_header(),
            timeout=5,
        )
        if response.status_code != 200:
            raise RuntimeError(f"objects failed with HTTP {response.status_code}")
        payload = _read_json_payload(response)
        if isinstance(payload, dict):
            yield _string_list(payload.get("objects"))
        elif isinstance(payload, list):
            yield _string_list(payload)
        else:
            yield []


def sync(*, verbose: bool = True) -> dict[str, int | TypeCounter]:
    """Synchronize objects with all configured peers."""

    peers = load_network_targets()
    local_ids = set(list_objects())
    overall_types: TypeCounter = Counter()
    imported_total = 0

    if verbose:
        print(f"[SYNC] starting sync with {len(peers)} peers")

    for peer in peers:
        summary = sync_peer(peer, local_ids, verbose=verbose)

        if verbose:
            if bool(summary["failed"]):
                print(f"[SYNC] {peer}: failed")
            else:
                print(
                    f"[SYNC] {peer}: {summary['missing']} missing, "
                    f"imported {summary['imported']} ({summarize_types(summary['types'])})"
                )

        overall_types.update(summary["types"])
        imported_total += int(summary["imported"])

    if verbose:
        print(
            f"[SYNC] complete: imported {imported_total} "
            f"({summarize_types(overall_types)})"
        )

    return {
        "peers": len(peers),
        "imported": imported_total,
        "types": overall_types,
    }


def recover_objects(
    owner_pubkey: str,
    object_ids: list[str],
    peers: list[str],
    *,
    verbose: bool = True,
) -> RecoverySummary:
    """Recover specific objects from peers during restore flows."""

    local_ids = set(list_objects())
    target_ids = [obj_id for obj_id in object_ids if obj_id not in local_ids]
    imported = 0
    types: TypeCounter = Counter()
    remaining = set(target_ids)

    if verbose:
        print(
            f"[RECOVERY] attempting to recover {len(target_ids)} object(s) "
            f"from {len(peers)} peer(s)"
        )

    for peer in peers:
        if not remaining:
            break

        for obj_id in list(remaining):
            obj = fetch_object(peer, obj_id)
            if obj is None:
                continue
            if receive_object(obj, verbose=verbose):
                pin_object(obj_id, "recovery")
                imported += 1
                types[obj.get("type", "object")] += 1
                remaining.discard(obj_id)

    if verbose:
        print(f"[RECOVERY] recovered {imported} object(s) ({summarize_types(types)})")
        if remaining:
            print(f"[RECOVERY] still missing {len(remaining)} object(s)")

    return {
        "owner_pubkey": owner_pubkey,
        "requested": len(target_ids),
        "imported": imported,
        "missing": sorted(remaining),
        "types": types,
    }


def recover_latest_iro(
    owner_pubkey: str,
    peers: list[str],
    *,
    verbose: bool = True,
) -> BeepObjectRecord | None:
    """Find and cache the newest IRO for a given owner across peers."""

    candidates = recover_iro_candidates(owner_pubkey, peers)
    latest_iro = max(
        candidates,
        key=lambda obj: (obj["timestamp"], obj.get("id") or ""),
        default=None,
    )
    if latest_iro and verbose:
        print(f"[RECOVERY] discovered IRO {latest_iro.get('id', '')}")
    if latest_iro:
        save_object(latest_iro, auto_push=False)
        iro_id = latest_iro.get("id")
        if iro_id:
            pin_object(iro_id, "iro")

    return latest_iro


def recover_iro_candidates(
    owner_pubkey: str,
    peers: list[str],
) -> list[BeepObjectRecord]:
    """Return all verified IRO candidates found for an owner across peers."""

    candidates: dict[str, BeepObjectRecord] = {}

    for peer in peers:
        try:
            for remote_ids in iter_inventory_pages(peer):
                for obj_id in remote_ids:
                    obj = fetch_object(peer, obj_id)
                    if obj is None:
                        continue
                    if obj.get("type") != "iro":
                        continue
                    if obj.get("author") != owner_pubkey:
                        continue
                    if not verify_object(obj):
                        continue
                    obj_id_value = obj.get("id")
                    if isinstance(obj_id_value, str):
                        candidates[obj_id_value] = obj
        except Exception:
            continue

    return sorted(candidates.values(), key=lambda obj: (obj["timestamp"], obj["id"]))


def _read_json_payload(response: requests.Response) -> object:
    """Safely decode JSON from a response."""

    try:
        return response.json()
    except ValueError:
        return None


def _string_list(value: object) -> list[str]:
    """Normalize a JSON array into a list of strings."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _looks_like_object(payload: object) -> bool:
    """Check whether a JSON payload resembles a stored object record."""

    if not isinstance(payload, dict):
        return False
    required_keys = {"type", "author", "content", "timestamp", "meta"}
    return required_keys.issubset(payload)


def _object_is_publicly_replicable(obj: BeepObjectRecord) -> bool:
    """Return whether an object can be pushed to general peers/relays."""

    if obj.get("type") == "room_event":
        return _room_scoped_object_is_public(obj)

    visibility = object_visibility(obj)
    if visibility == "public":
        return True
    if visibility == "public_encrypted":
        return True
    if obj.get("type") != "room_message":
        return False

    return _room_scoped_object_is_public(obj)


def _room_scoped_object_is_public(obj: BeepObjectRecord) -> bool:
    """Return whether a room-scoped object belongs to a public room."""

    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return False

    room_id = meta.get("room")
    if not isinstance(room_id, str) or not room_id:
        return False

    try:
        from storage.room_service import RoomService

        room = RoomService().build_room_state(room_id)
    except Exception:
        return False

    if room is None:
        return False
    return room.get("type") != "private"
