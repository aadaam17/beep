import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from commands.node import dispatch as node_dispatch
from commands.storage import dispatch as storage_dispatch
from commands.sync import SyncCommand


class CommandCompatibilityTests(unittest.TestCase):
    @patch("commands.sync.sync_now")
    def test_sync_command_uses_canonical_sync(self, mock_sync):
        mock_sync.return_value = {"peers": 2, "imported": 4, "types": {}}
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            SyncCommand.dispatch("sync", "", state)

        mock_sync.assert_called_once_with(verbose=True)
        self.assertIn("[SYNC] done: 4 imported from 2 peer(s)", output.getvalue())

    @patch("commands.node.run_node")
    def test_node_command_uses_canonical_node_runner(self, mock_run_node):
        state = SimpleNamespace(user="alice", pubkey="pubkey_1")

        node_dispatch("node", "run --port 9001", state)

        mock_run_node.assert_called_once_with(
            port=9001,
            session_username="alice",
            session_pubkey="pubkey_1",
        )

    @patch("commands.storage.retention_summary")
    def test_storage_status_uses_retention_summary(self, mock_summary):
        mock_summary.return_value = {
            "total_objects": 5,
            "retained_objects": 3,
            "prunable_objects": 2,
            "reasons": {"authored": 2, "iro": 1},
        }
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            storage_dispatch("storage", "status", state)

        mock_summary.assert_called_once_with()
        rendered = output.getvalue()
        self.assertIn("[STORAGE] Retention summary", rendered)
        self.assertIn("Total objects: 5", rendered)
        self.assertIn(" - authored: 2", rendered)

    @patch("commands.storage.prune_objects")
    def test_storage_prune_apply_uses_prune_objects(self, mock_prune):
        mock_prune.return_value = {"removed_count": 2, "removed_ids": ["a", "b"]}
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            storage_dispatch("storage", "prune --apply", state)

        mock_prune.assert_called_once_with(dry_run=False)
        rendered = output.getvalue()
        self.assertIn("[STORAGE] Pruned: 2 object(s)", rendered)
        self.assertIn(" - a", rendered)


if __name__ == "__main__":
    unittest.main()
