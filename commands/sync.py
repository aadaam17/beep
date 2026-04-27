from network.replication import Replicator
from network.smart_replication import SmartReplicator

# class SyncCommand:
#     @staticmethod
#     def dispatch(cmd, args, state):
#         if cmd != "sync":
#             return

#         if not state.peers:
#             print("[SYNC] No peers configured")
#             return

#         print(f"[SYNC] syncing with {len(state.peers)} peers...")
#         peers = state.peers
#         Replicator(peers).sync()

#         print("[SYNC] done")

class SyncCommand:
    @staticmethod
    def dispatch(cmd, args, state):
        if cmd != "sync":
            return

        if not state.peers:
            print("[SYNC] No peers configured")
            return

        print(f"[SYNC] syncing with {len(state.peers)} peers...")
        peers = state.peers
        SmartReplicator(peers).sync(state)

        print("[SYNC] done")