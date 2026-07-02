import tempfile
import unittest
from contextlib import redirect_stdout
import io
from pathlib import Path
from unittest.mock import patch

from commands import config_cmd
from storage import app_config
from storage import network_policy


class AppConfigTests(unittest.TestCase):
    def test_load_app_config_reads_first_existing_toml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "beep.toml"
            path.write_text(
                """
[node]
enabled = true

[network]
strategy = "relay-first"
""".strip(),
                encoding="utf-8",
            )

            with patch.object(app_config, "config_search_paths", return_value=[path]):
                result = app_config.load_app_config()

        self.assertEqual(result["path"], str(path))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])
        self.assertTrue(result["data"]["node"]["enabled"])

    def test_network_policy_overrides_maps_toml_fields(self):
        data = {
            "node": {"enabled": True, "relay_only": True},
            "network": {"strategy": "relay-first", "public_endpoint": "https://relay.example.net"},
            "relay": {"retention_limit": 123, "max_object_bytes": 456},
        }

        with patch.object(
            app_config,
            "load_app_config",
            return_value={
                "path": "beep.toml",
                "data": data,
                "errors": [],
                "warnings": [],
            },
        ):
            overrides = app_config.network_policy_overrides()

        self.assertEqual(overrides["node_autostart"], True)
        self.assertEqual(overrides["relay_only_mode"], True)
        self.assertEqual(overrides["strategy"], "relay-first")
        self.assertEqual(overrides["public_endpoint"], "https://relay.example.net")
        self.assertEqual(overrides["relay_retention_limit"], 123)
        self.assertEqual(overrides["max_object_bytes"], 456)

    def test_load_network_policy_applies_config_overrides_to_defaults(self):
        with patch.object(network_policy, "read_json_with_backup", return_value=None), patch.object(
            network_policy,
            "network_policy_overrides",
            return_value={"node_autostart": True, "strategy": "direct-only"},
        ):
            policy = network_policy.load_network_policy()

        self.assertTrue(policy["node_autostart"])
        self.assertEqual(policy["strategy"], "direct-only")

    def test_validate_rejects_bad_values(self):
        errors, warnings = app_config.validate_app_config(
            {
                "network": {"strategy": "bad"},
                "relay": {"max_object_bytes": 0},
                "peers": [123],
                "unknown": {},
            }
        )

        self.assertIn("network.strategy must be prefer-direct, direct-only, or relay-first", errors)
        self.assertIn("relay.max_object_bytes must be a positive integer", errors)
        self.assertIn("peers must contain only strings", errors)
        self.assertIn("unknown section ignored: unknown", warnings)

    def test_network_peer_auth_token_can_come_from_environment(self):
        data = {
            "network": {
                "peer_auth_required": True,
                "peer_auth_token_env": "BEEP_TEST_PEER_TOKEN",
            }
        }

        with patch.object(
            app_config,
            "load_app_config",
            return_value={
                "path": "beep.toml",
                "data": data,
                "errors": [],
                "warnings": [],
            },
        ), patch.dict("os.environ", {"BEEP_TEST_PEER_TOKEN": "secret"}):
            overrides = app_config.network_policy_overrides()

        self.assertEqual(overrides["peer_auth_token"], "secret")

    def test_write_default_config_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "beep.toml"
            created = app_config.write_default_config(path)

            with self.assertRaises(FileExistsError):
                app_config.write_default_config(path)

        self.assertEqual(created, path)

    def test_config_validate_command_reports_valid_file(self):
        with patch.object(
            config_cmd,
            "load_app_config",
            return_value={
                "path": "beep.toml",
                "data": {"node": {}},
                "errors": [],
                "warnings": [],
            },
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                config_cmd.dispatch("config", "validate", object())

        self.assertIn("[CONFIG] valid: beep.toml", output.getvalue())


if __name__ == "__main__":
    unittest.main()
