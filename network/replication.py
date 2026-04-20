import requests
from core.object_store import ObjectStore
from core.verify import verify_object


store = ObjectStore()


class Replicator:
    def __init__(self, peers: list[str]):
        self.peers = peers

    def sync(self):
        """
        Pull missing objects from peers.
        """

        local_ids = set(store.list_ids())

        for peer in self.peers:
            try:
                remote_ids = self._get_remote_ids(peer)
            except Exception as e:
                print(f"[SYNC] Peer error {peer}: {e}")
                continue

            missing = remote_ids - local_ids

            print(f"[SYNC] Peer {peer}: {len(missing)} missing objects")

            for obj_id in missing:
                obj = self._fetch_object(peer, obj_id)
                if not obj:
                    continue

                # STEP 7 — enforce signed object verification
                if not verify_object(obj):
                    print(f"[SYNC] Invalid object rejected: {obj_id}")
                    continue

                store.put(obj)
                print(f"[SYNC] Imported {obj_id}")

    def _get_remote_ids(self, peer):
        res = requests.get(f"{peer}/objects")
        res.raise_for_status()
        return set(res.json()["objects"])

    def _fetch_object(self, peer, obj_id):
        try:
            res = requests.get(f"{peer}/object/{obj_id}")
            res.raise_for_status()
            return res.json()
        except Exception:
            return None