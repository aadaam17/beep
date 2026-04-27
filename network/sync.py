from collections import Counter

import requests

from core.verify import verify_object
from network.peers import load_peers
from storage.objects import get_object, list_objects, save_object

TYPE_LABELS = {
    "post": "posts",
    "comment": "comments",
    "share": "shares",
    "quote": "quotes",
    "profile": "profiles",
    "follow": "follows",
    "chat": "chats",
    "dm": "dms",
    "room": "rooms",
    "room_event": "room events",
    "room_message": "room messages",
}


def summarize_types(counter: Counter) -> str:
    if not counter:
        return "nothing new"

    parts = []
    for obj_type, count in sorted(counter.items()):
        label = TYPE_LABELS.get(obj_type, obj_type)
        parts.append(f"{count} {label}")
    return ", ".join(parts)


def receive_object(obj: dict) -> bool:
    if not verify_object(obj):
        print("[SYNC] rejected untrusted object")
        return False

    stored = save_object(obj, auto_push=False)
    if stored:
        print(f"[SYNC] accepted {obj.get('type', 'object')} {obj.get('id', '')}".strip())
    return stored


def push_object(peer, obj):
    try:
        response = requests.post(f"{peer}/object", json=obj, timeout=5)
        return response.status_code in (200, 201, 202)
    except Exception as e:
        print(f"[SYNC] push failed to {peer}: {e}")
        return False


def push_object_to_peers(obj: dict, peers=None):
    peers = peers if peers is not None else load_peers()
    pushed = 0

    for peer in peers:
        if push_object(peer, obj):
            pushed += 1

    return pushed


def push_existing_object(obj_id: str, peers=None):
    obj = get_object(obj_id)
    if not obj:
        return 0
    return push_object_to_peers(obj, peers=peers)


def fetch_object(peer, obj_id):
    try:
        r = requests.get(f"{peer}/object/{obj_id}", timeout=5)
        if r.status_code == 200:
            payload = r.json()
            if isinstance(payload, dict) and payload.get("error"):
                return None
            return payload
    except Exception as e:
        print(f"[SYNC] fetch failed from {peer}: {e}")
    return None


def sync_peer(peer, local_ids):
    summary = {
        "peer": peer,
        "missing": 0,
        "imported": 0,
        "types": Counter(),
        "failed": False,
    }

    try:
        r = requests.get(f"{peer}/objects", timeout=5)
        if r.status_code != 200:
            summary["failed"] = True
            return summary

        payload = r.json()
        if isinstance(payload, dict):
            remote_ids = set(payload.get("objects", []))
        elif isinstance(payload, list):
            remote_ids = set(payload)
        else:
            remote_ids = set()

        missing = remote_ids - local_ids
        summary["missing"] = len(missing)

        for obj_id in missing:
            obj = fetch_object(peer, obj_id)
            if not obj:
                continue

            if receive_object(obj):
                obj_type = obj.get("type", "object")
                summary["imported"] += 1
                summary["types"][obj_type] += 1
                local_ids.add(obj_id)

    except Exception as e:
        print(f"[SYNC] peer failed {peer}: {e}")
        summary["failed"] = True

    return summary


def sync(*, verbose: bool = True):
    peers = load_peers()
    local_ids = set(list_objects())
    overall_types = Counter()
    imported_total = 0

    if verbose:
        print(f"[SYNC] starting sync with {len(peers)} peers")

    for peer in peers:
        summary = sync_peer(peer, local_ids)

        if verbose:
            if summary["failed"]:
                print(f"[SYNC] {peer}: failed")
            else:
                print(
                    f"[SYNC] {peer}: {summary['missing']} missing, "
                    f"imported {summary['imported']} ({summarize_types(summary['types'])})"
                )

        overall_types.update(summary["types"])
        imported_total += summary["imported"]

    if verbose:
        print(f"[SYNC] complete: imported {imported_total} ({summarize_types(overall_types)})")

    return {
        "peers": len(peers),
        "imported": imported_total,
        "types": overall_types,
    }
