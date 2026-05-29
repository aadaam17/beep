# commands/sync.py
"""Sync command to synchronize data with peers."""

from network.sync import sync as sync_now
from core.types import CommandState


class SyncCommand:
    @staticmethod
    def dispatch(cmd: str, args: str, state: CommandState) -> None:
        if cmd != "sync":
            return

        result = sync_now(verbose=True)

        print(
            f"[SYNC] done: {result['imported']} imported from {result['peers']} peer(s)"
        )