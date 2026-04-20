# network/sync.py

import requests

from core.verify import verify_object
from core.object import BeepObject
from storage.objects import save_object, list_objects
from network.peers import load_peers


# =========================================================
# OBJECT PIPELINE (single entry for incoming data)
# =========================================================
def receive_object(obj: dict) -> bool:
    """
    Incoming network object pipeline (single source of truth)
    """

    if not verify_object(obj):
        print("[SYNC] rejected untrusted object")
        return False

    save_object(BeepObject.from_dict(obj))
    
    print("[SYNC] accepted object")
    return True

# =========================================================
# TRANSPORT LAYER
# =========================================================
def push_object(peer, obj):
    try:
        requests.post(f"{peer}/object", json=obj, timeout=5)
    except Exception as e:
        print(f"[SYNC] push failed to {peer}: {e}")


def fetch_object(peer, obj_id):
    try:
        r = requests.get(f"{peer}/object/{obj_id}", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[SYNC] fetch failed from {peer}: {e}")
    return None


# =========================================================
# SYNC ENGINE
# =========================================================
def sync_peer(peer, local_ids):
    try:
        r = requests.get(f"{peer}/objects", timeout=5)
        if r.status_code != 200:
            return

        remote_ids = set(r.json())
        missing = remote_ids - local_ids

        print(f"[SYNC] {peer}: {len(missing)} missing objects")

        for obj_id in missing:
            obj = fetch_object(peer, obj_id)
            if not obj:
                continue

            # ALWAYS go through pipeline (important fix)
            receive_object(obj)

    except Exception as e:
        print(f"[SYNC] peer failed {peer}: {e}")


def sync():
    peers = load_peers()
    local_ids = set(list_objects())

    print(f"[SYNC] starting sync with {len(peers)} peers")

    for peer in peers:
        sync_peer(peer, local_ids)

    print("[SYNC] complete")