import requests
import time

from core.verify import verify_object
from core.identity import resolve_username
from core.index import ObjectIndex
from storage.objects import save_object
from storage.profile import get_user


class SmartReplicator:
    def __init__(self, peers):
        self.peers = peers
        self.index = ObjectIndex()

    # -------------------------
    # MAIN ENTRY
    # -------------------------
    def sync(self, state):
        print("[SMART SYNC] Starting...")

        local_ids = set(self.index.get_all())

        for peer in self.peers:
            try:
                self._sync_peer(peer, local_ids, state)
            except Exception as e:
                print(f"[SMART SYNC] Peer failed: {peer} -> {e}")

        print("[SMART SYNC] Done")

    # -------------------------
    # SYNC ONE PEER
    # -------------------------
    def _sync_peer(self, peer, local_ids, state):
        print(f"[SMART SYNC] Checking {peer}")

        # Ask peer for object list
        res = requests.get(f"{peer}/inventory").json()

        peer_ids = set(res.get("ids", []))
        meta = res.get("meta", {})

        # Find missing objects
        missing = peer_ids - local_ids

        if not missing:
            print("[SMART SYNC] No new objects")
            return

        # Score them
        ranked = self._rank_objects(missing, meta, state)

        # Fetch top N
        for obj_id in ranked[:50]:
            obj = requests.get(f"{peer}/object/{obj_id}").json()

            if verify_object(obj):
                self._store_object(obj)
            else:
                print("[SMART SYNC] Rejected untrusted object")

    # -------------------------
    # RANKING LOGIC
    # -------------------------
    def _rank_objects(self, ids, meta, state):
        scored = []

        user = get_user(state.user) if state.user else None
        following = set(user.get("following", [])) if user else set()

        now = time.time()

        for obj_id in ids:
            score = 0
            info = meta.get(obj_id, {})

            author = info.get("author")
            timestamp = info.get("timestamp", 0)

            # ---- FOLLOW PRIORITY ----
            if author in following:
                score += 50

            # ---- TRUST PRIORITY ----
            # (you can expand later)
            if author:
                score += 10

            # ---- RECENCY ----
            age = now - timestamp
            if age < 3600:
                score += 20
            elif age < 86400:
                score += 10

            scored.append((score, obj_id))

        scored.sort(reverse=True)
        return [obj_id for _, obj_id in scored]

    # -------------------------
    # STORE OBJECT
    # -------------------------
    def _store_object(self, obj):
        save_object(obj)
        self.index.index(obj)

        name = resolve_username(obj["author"])
        print(f"[SYNC] Stored object from {name}")
