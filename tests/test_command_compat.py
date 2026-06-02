import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import app
import cli
from commands.node import dispatch as node_dispatch
from commands.connect import dispatch as connect_dispatch
from commands.network import dispatch as network_dispatch
from commands.relay import dispatch as relay_dispatch
from commands.storage import dispatch as storage_dispatch
from commands.sync import SyncCommand
from state import AppState, Mode


class CommandCompatibilityTests(unittest.TestCase):
    def test_shell_prompt_uses_explicit_shell_prefix(self):
        original_state = app.state
        shell_state = AppState()
        shell_state.mode = Mode.CHAT
        shell_state.current_chat = "bob"
        app.state = shell_state
        try:
            self.assertEqual(app.get_prompt(), "[shell:chat:@bob] > ")
        finally:
            app.state = original_state

    def test_shell_context_banner_announces_followed_feed(self):
        original_state = app.state
        shell_state = AppState()
        shell_state.mode = Mode.FOLLOWED_FYP
        app.state = shell_state
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                app._announce_shell_context_change(Mode.GLOBAL_FYP, None, None)
            self.assertIn("[SHELL] Context -> feed followed", output.getvalue())
        finally:
            app.state = original_state

    @patch("cli.run_command_shell")
    def test_cli_without_args_defaults_to_command_mode(
        self,
        mock_run_command_shell,
    ):
        cli.main([])
        mock_run_command_shell.assert_called_once_with()

    @patch("cli.run_shell")
    def test_cli_shell_arg_enters_interactive_mode(self, mock_run_shell):
        cli.main(["shell"])
        mock_run_shell.assert_called_once_with()

    @patch("app.launch_textual_shell")
    def test_run_shell_launches_textual_ui(self, mock_launch_textual_shell):
        app.run_shell()
        mock_launch_textual_shell.assert_called_once_with()

    @patch("app.launch_textual_shell")
    def test_execute_beep_shell_command_launches_textual_ui(
        self,
        mock_launch_textual_shell,
    ):
        app.execute_beep_parts(["shell"])
        mock_launch_textual_shell.assert_called_once_with()

    @patch("app.run_live_mode")
    def test_execute_beep_live_command_uses_live_mode(self, mock_run_live_mode):
        app.execute_beep_parts(["fyp", "--live"])
        mock_run_live_mode.assert_called_once_with(["fyp", "--live"])

    @patch("app._run_legacy_shell")
    def test_run_command_shell_uses_legacy_text_mode(self, mock_run_legacy_shell):
        app.run_command_shell()
        mock_run_legacy_shell.assert_called_once_with()

    @patch("cli.run_command_shell")
    def test_cli_direct_argv_command_falls_back_to_command_shell(
        self,
        mock_run_command_shell,
    ):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.main(["post", "hello"])
        mock_run_command_shell.assert_called_once_with()
        self.assertIn("Ignoring direct argv command: post hello", output.getvalue())

    @patch("cli.run_command_shell")
    def test_cli_live_argv_command_falls_back_to_command_shell(
        self,
        mock_run_command_shell,
    ):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.main(["fyp", "--live"])
        mock_run_command_shell.assert_called_once_with()
        self.assertIn("Ignoring direct argv command: fyp --live", output.getvalue())

    @patch("commands.sync.sync_now")
    def test_sync_command_uses_canonical_sync(self, mock_sync):
        mock_sync.return_value = {"peers": 2, "imported": 4, "types": {}}
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            SyncCommand.dispatch("sync", "", state)

        mock_sync.assert_called_once_with(verbose=True)
        self.assertIn("[SYNC] done: 4 imported from 2 peer(s)", output.getvalue())

    @patch("commands.node._ensure_server_dependencies", return_value=True)
    @patch("commands.node.run_node")
    def test_node_command_uses_canonical_node_runner(
        self,
        mock_run_node,
        mock_server_dependencies,
    ):
        state = SimpleNamespace(user="alice", pubkey="pubkey_1")

        node_dispatch("node", "run --port 9001", state)

        mock_server_dependencies.assert_called_once_with()
        mock_run_node.assert_called_once_with(
            port=9001,
            session_username="alice",
            session_pubkey="pubkey_1",
        )

    @patch("commands.network.load_node_runtime")
    @patch("commands.network.order_network_targets")
    @patch("commands.network.load_relays")
    @patch("commands.network.load_peers")
    @patch("commands.network.load_network_policy")
    def test_network_status_renders_summary(
        self,
        mock_policy,
        mock_peers,
        mock_relays,
        mock_targets,
        mock_runtime,
    ):
        mock_policy.return_value = {
            "relay_enabled": True,
            "node_autostart": True,
            "strategy": "prefer-direct",
            "presence_ttl_seconds": 86400,
            "presence_refresh_seconds": 900,
            "public_endpoint": "https://relay.example.net",
        }
        mock_peers.return_value = ["http://peer-a"]
        mock_relays.return_value = ["http://relay-a"]
        mock_targets.return_value = ["http://peer-a", "http://relay-a"]
        mock_runtime.return_value = {
            "host": "127.0.0.1",
            "port": 9001,
            "url": "http://127.0.0.1:9001",
            "username": "alice",
            "pubkey": "pubkey_1",
            "pid": 999,
        }
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            network_dispatch("network", "status", state)

        rendered = output.getvalue()
        self.assertIn("[NETWORK] Status", rendered)
        self.assertIn("discovery targets: 2", rendered)
        self.assertIn("https://relay.example.net", rendered)
        self.assertIn("http://127.0.0.1:9001", rendered)

    @patch("commands.network.load_network_policy")
    @patch("commands.network.load_relays")
    @patch("commands.network.load_peers")
    def test_network_setup_guides_empty_network(
        self,
        mock_peers,
        mock_relays,
        mock_policy,
    ):
        mock_peers.return_value = []
        mock_relays.return_value = []
        mock_policy.return_value = {
            "relay_enabled": True,
            "node_autostart": True,
            "strategy": "prefer-direct",
            "presence_ttl_seconds": 86400,
            "presence_refresh_seconds": 900,
            "public_endpoint": "",
        }
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            network_dispatch("network", "setup", state)

        rendered = output.getvalue()
        self.assertIn("This node is not connected to anyone yet", rendered)
        self.assertIn("beep network setup --relay <url>", rendered)

    @patch("commands.network.add_relay")
    def test_network_setup_adds_relay(self, mock_add_relay):
        mock_add_relay.return_value = "https://relay.example.net"
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            network_dispatch("network", "setup --relay https://relay.example.net", state)

        mock_add_relay.assert_called_once_with("https://relay.example.net")
        self.assertIn("Added relay https://relay.example.net", output.getvalue())

    @patch("commands.network.probe_endpoint", return_value="unreachable")
    @patch("commands.network.order_network_targets", return_value=["http://peer-a"])
    @patch("commands.network.load_relays", return_value=[])
    @patch("commands.network.load_peers", return_value=["http://peer-a"])
    def test_network_check_reports_unreachable_targets(
        self,
        mock_peers,
        mock_relays,
        mock_targets,
        mock_probe,
    ):
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            network_dispatch("network", "check", state)

        mock_probe.assert_called_once_with("http://peer-a")
        rendered = output.getvalue()
        self.assertIn("unreachable", rendered)
        self.assertIn("Reachable targets: 0/1", rendered)

    @patch("commands.storage.retention_summary")
    def test_storage_status_uses_retention_summary(self, mock_summary):
        mock_summary.return_value = {
            "total": 5,
            "prunable": 2,
            "retained": {"authored": 2, "iro": 1},
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
        mock_prune.return_value = {
            "retained": [],
            "prunable": ["a", "b"],
            "pruned": ["a", "b"],
            "stale_pins_removed": [],
        }
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            storage_dispatch("storage", "prune --apply", state)

        mock_prune.assert_called_once_with(dry_run=False)
        rendered = output.getvalue()
        self.assertIn("[STORAGE] Pruned: 2 object(s)", rendered)
        self.assertIn(" - a", rendered)

    @patch("commands.connect.get_user")
    def test_connect_without_args_shows_local_handle(self, mock_get_user):
        mock_get_user.return_value = {
            "username": "alice",
            "pubkey": "abcdef1234567890",
        }
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "", state)

        rendered = output.getvalue()
        self.assertIn("[CONNECT] Your Beep handle: alice#abcdef", rendered)
        self.assertIn("[CONNECT] Network strategy:", rendered)

    @patch("commands.connect.probe_endpoint", return_value="reachable")
    @patch("commands.connect.sync")
    @patch("commands.connect.add_peer")
    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.load_peers")
    def test_connect_discovers_peer_and_syncs(
        self,
        mock_load_peers,
        mock_resolve_identity,
        mock_add_peer,
        mock_sync,
        mock_probe,
    ):
        mock_load_peers.return_value = ["http://peer-a"]
        mock_resolve_identity.return_value = [
            {
                "username": "bob",
                "pubkey": "b" * 64,
                "handle": "bob#bbbbbb",
                "endpoint": "http://127.0.0.1:9911",
                "stale_endpoint": "http://127.0.0.1:9911",
                "presence_state": "fresh",
                "relay_hints": [],
            }
        ]
        mock_add_peer.return_value = "http://127.0.0.1:9911"
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        mock_resolve_identity.assert_called_once_with("bob#bbbbbb", ["http://peer-a"])
        mock_probe.assert_called_once_with("http://127.0.0.1:9911")
        mock_add_peer.assert_called_once_with("http://127.0.0.1:9911")
        mock_sync.assert_called_once_with(verbose=False)
        self.assertIn("[CONNECT] Connected to bob#bbbbbb", output.getvalue())

    @patch("commands.connect.sync")
    @patch("commands.connect.add_relay")
    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.load_relays")
    @patch("commands.connect.load_peers")
    def test_connect_uses_relay_hint_when_no_direct_endpoint(
        self,
        mock_load_peers,
        mock_load_relays,
        mock_resolve_identity,
        mock_add_relay,
        mock_sync,
    ):
        mock_load_peers.return_value = []
        mock_load_relays.return_value = ["http://relay-a"]
        mock_resolve_identity.return_value = [
            {
                "username": "bob",
                "pubkey": "b" * 64,
                "handle": "bob#bbbbbb",
                "endpoint": None,
                "stale_endpoint": None,
                "presence_state": "none",
                "relay_hints": ["http://relay-a"],
            }
        ]
        mock_add_relay.return_value = "http://relay-a"
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        mock_resolve_identity.assert_called_once_with("bob#bbbbbb", ["http://relay-a"])
        mock_add_relay.assert_called_once_with("http://relay-a")
        mock_sync.assert_called_once_with(verbose=False)
        self.assertIn("relay-assisted discovery", output.getvalue())

    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.load_relays")
    @patch("commands.connect.load_peers")
    def test_connect_reports_when_no_discovery_targets_exist(
        self,
        mock_load_peers,
        mock_load_relays,
        mock_resolve_identity,
    ):
        mock_load_peers.return_value = []
        mock_load_relays.return_value = []
        mock_resolve_identity.return_value = []
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        self.assertIn("No peers or relays are configured", output.getvalue())

    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.relay_enabled", return_value=False)
    @patch("commands.connect.load_network_policy")
    @patch("commands.connect.load_peers")
    def test_connect_reports_disabled_relay_policy(
        self,
        mock_load_peers,
        mock_load_policy,
        mock_relay_enabled,
        mock_resolve_identity,
    ):
        mock_load_peers.return_value = []
        mock_load_policy.return_value = {
            "relay_enabled": False,
            "node_autostart": True,
            "strategy": "prefer-direct",
            "presence_ttl_seconds": 86400,
            "presence_refresh_seconds": 900,
            "public_endpoint": "",
        }
        mock_resolve_identity.return_value = [
            {
                "username": "bob",
                "pubkey": "b" * 64,
                "handle": "bob#bbbbbb",
                "endpoint": None,
                "stale_endpoint": None,
                "presence_state": "none",
                "relay_hints": ["http://relay-a"],
            }
        ]
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        self.assertIn("relay use is disabled by policy", output.getvalue())

    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.load_relays")
    @patch("commands.connect.load_peers")
    @patch("commands.connect.load_network_policy")
    @patch("commands.connect.order_network_targets", return_value=[])
    def test_connect_reports_direct_only_skips_relays(
        self,
        mock_order_targets,
        mock_load_policy,
        mock_load_peers,
        mock_load_relays,
        mock_resolve_identity,
    ):
        mock_load_policy.return_value = {
            "relay_enabled": True,
            "node_autostart": True,
            "strategy": "direct-only",
            "presence_ttl_seconds": 86400,
            "presence_refresh_seconds": 900,
            "public_endpoint": "",
        }
        mock_load_peers.return_value = []
        mock_load_relays.return_value = ["http://relay-a"]
        mock_resolve_identity.return_value = []
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        mock_order_targets.assert_called_once_with([], ["http://relay-a"])
        mock_resolve_identity.assert_called_once_with("bob#bbbbbb", [])
        self.assertIn("Strategy is direct-only", output.getvalue())

    @patch("commands.connect.probe_endpoint", return_value="unreachable")
    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.load_peers")
    def test_connect_reports_known_endpoint_but_down(
        self,
        mock_load_peers,
        mock_resolve_identity,
        mock_probe,
    ):
        mock_load_peers.return_value = ["http://peer-a"]
        mock_resolve_identity.return_value = [
            {
                "username": "bob",
                "pubkey": "b" * 64,
                "handle": "bob#bbbbbb",
                "endpoint": "http://bob-node",
                "stale_endpoint": "http://bob-node",
                "presence_state": "fresh",
                "relay_hints": [],
            }
        ]
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        mock_probe.assert_called_once_with("http://bob-node")
        self.assertIn("direct endpoint is currently down", output.getvalue())

    @patch("commands.connect.resolve_identity")
    @patch("commands.connect.load_relays")
    @patch("commands.connect.load_peers")
    def test_connect_reports_stale_presence_before_relay_fallback(
        self,
        mock_load_peers,
        mock_load_relays,
        mock_resolve_identity,
    ):
        mock_load_peers.return_value = []
        mock_load_relays.return_value = []
        mock_resolve_identity.return_value = [
            {
                "username": "bob",
                "pubkey": "b" * 64,
                "handle": "bob#bbbbbb",
                "endpoint": None,
                "stale_endpoint": "http://old-bob-node",
                "presence_state": "stale",
                "relay_hints": [],
            }
        ]
        state = SimpleNamespace(user="alice")

        output = io.StringIO()
        with redirect_stdout(output):
            connect_dispatch("connect", "bob#bbbbbb", state)

        rendered = output.getvalue()
        self.assertIn("latest known direct endpoint is stale", rendered)
        self.assertIn("http://old-bob-node", rendered)

    @patch("commands.relay.update_network_policy")
    def test_relay_policy_set_strategy_updates_policy(self, mock_update_policy):
        mock_update_policy.return_value = {
            "relay_enabled": True,
            "node_autostart": True,
            "strategy": "relay-first",
            "presence_ttl_seconds": 86400,
            "presence_refresh_seconds": 900,
            "public_endpoint": "",
        }
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            relay_dispatch("relay", "policy set strategy relay-first", state)

        mock_update_policy.assert_called_once_with(strategy="relay-first")
        self.assertIn("strategy set to relay-first", output.getvalue())

    @patch("commands.relay.update_network_policy")
    def test_relay_policy_set_public_endpoint_normalizes_url(self, mock_update_policy):
        mock_update_policy.return_value = {
            "relay_enabled": True,
            "node_autostart": True,
            "strategy": "prefer-direct",
            "presence_ttl_seconds": 86400,
            "presence_refresh_seconds": 900,
            "public_endpoint": "https://relay.example.net",
        }
        state = SimpleNamespace()

        output = io.StringIO()
        with redirect_stdout(output):
            relay_dispatch(
                "relay",
                "policy set public-endpoint https://relay.example.net/",
                state,
            )

        mock_update_policy.assert_called_once_with(
            public_endpoint="https://relay.example.net"
        )
        self.assertIn("public endpoint: https://relay.example.net", output.getvalue())


if __name__ == "__main__":
    unittest.main()
