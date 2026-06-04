import io
import tempfile
import time
import unittest
import json
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commands import auth
from commands import connect as connect_command
from collections import Counter
from cryptography.hazmat.primitives import serialization
from core.object import BeepObject
from crypto import keys as crypto_keys
from crypto import mnemonic as crypto_mnemonic
from crypto import seed as crypto_seed
from crypto import sign as crypto_sign
from network import node as network_node
from network import node_manager as network_node_manager
from network import peers as network_peers
from network import sync as network_sync
from storage import network_policy as storage_network_policy
from storage import relay as storage_relay
from state import AppState
from storage import backup as storage_backup
from storage import iro as storage_iro
from storage import objects as storage_objects
from storage import presence as storage_presence
from storage import profile as storage_profile
from storage import restore as storage_restore
from storage import session as storage_session
from storage.objects import pinned_objects
from storage.chat_service import ChatService
from storage.room_service import RoomService
from storage.crypto import encrypt_for_recipients, encryption_pubkey_to_str


class IsolatedStorageTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.beep_home = self.root / ".beep"
        self.storage_root = self.beep_home / "beep_storage"
        self.objects_dir = self.storage_root / "objects"
        self.users_dir = self.storage_root / "users"
        self.sign_dir = self.storage_root / "signing"
        self.seed_dir = self.storage_root / "seeds"
        self.chats_dir = self.storage_root / "chats"
        self.pins_file = self.storage_root / "pins.json"
        self.session_file = self.beep_home / "beep_session.json"
        self.peer_file = self.beep_home / "peers.json"
        self.relay_file = self.beep_home / "relays.json"
        self.policy_file = self.beep_home / "network_policy.json"
        self.node_runtime_file = self.beep_home / "node_runtime.json"
        self.user_storage_file = self.beep_home / "beep_users.json"
        self.chat_index_file = self.chats_dir / "index.json"

        for path in [
            self.beep_home,
            self.storage_root,
            self.objects_dir,
            self.users_dir,
            self.sign_dir,
            self.seed_dir,
            self.chats_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        self.patches = ExitStack()
        self.patches.enter_context(
            patch.object(storage_profile, "USER_STORAGE_FILE", self.user_storage_file)
        )
        self.patches.enter_context(
            patch.object(storage_objects, "OBJECTS_DIR", self.objects_dir)
        )
        self.patches.enter_context(
            patch.object(storage_objects, "PINS_FILE", self.pins_file)
        )
        self.patches.enter_context(
            patch.object(crypto_keys, "USER_DIR", self.users_dir)
        )
        self.patches.enter_context(
            patch.object(crypto_sign, "SIGN_DIR", self.sign_dir)
        )
        self.patches.enter_context(
            patch.object(crypto_seed, "SEED_DIR", self.seed_dir)
        )
        self.patches.enter_context(
            patch.object(storage_session, "SESSION_FILE", self.session_file)
        )
        self.patches.enter_context(
            patch.object(storage_backup, "USER_STORAGE_FILE", self.user_storage_file)
        )
        self.patches.enter_context(
            patch.object(storage_backup, "RSA_USER_DIR", self.users_dir)
        )
        self.patches.enter_context(
            patch.object(storage_backup, "SIGN_DIR", self.sign_dir)
        )
        self.patches.enter_context(
            patch.object(storage_backup, "SEED_DIR", self.seed_dir)
        )
        self.patches.enter_context(
            patch.object(network_peers, "PEER_FILE", self.peer_file)
        )
        self.patches.enter_context(
            patch.object(storage_relay, "RELAY_FILE", self.relay_file)
        )
        self.patches.enter_context(
            patch.object(storage_network_policy, "POLICY_FILE", self.policy_file)
        )
        self.patches.enter_context(
            patch.object(network_node_manager, "RUNTIME_FILE", self.node_runtime_file)
        )
        self.patches.enter_context(
            patch.object(network_sync, "load_network_targets", return_value=[])
        )

        from storage import chat_service

        self.patches.enter_context(
            patch.object(chat_service, "CHATS_DIR", self.chats_dir)
        )
        self.patches.enter_context(
            patch.object(chat_service, "CHAT_INDEX_FILE", self.chat_index_file)
        )

    def tearDown(self):
        self.patches.close()
        self.tempdir.cleanup()

    def create_user(self, username, password="pass123"):
        return storage_profile.create_user(username, password)

    def enable_legacy_rsa(self, username):
        _, rsa_public = crypto_keys.load_or_create_keys(username)
        user = storage_profile.get_user(username)
        storage_profile.update_user(
            username,
            {
                **user,
                "rsa_pubkey": encryption_pubkey_to_str(rsa_public),
                "rsa_fingerprint": storage_profile._rsa_fingerprint(
                    encryption_pubkey_to_str(rsa_public)
                ),
            },
        )


class EndToEndFlowTests(IsolatedStorageTestCase):
    def test_follow_flow_updates_effective_social_graph(self):
        alice = self.create_user("alice")
        bob = self.create_user("bob")

        storage_profile.follow(alice["pubkey"], bob["pubkey"])

        self.assertIn(
            bob["pubkey"],
            storage_profile.get_effective_following(alice["pubkey"]),
        )
        self.assertIn(
            alice["pubkey"],
            storage_profile.get_effective_followers(bob["pubkey"]),
        )

        time.sleep(1)
        storage_profile.unfollow(alice["pubkey"], bob["pubkey"])

        self.assertNotIn(
            bob["pubkey"],
            storage_profile.get_effective_following(alice["pubkey"]),
        )

    def test_create_user_publishes_decryptable_iro(self):
        alice = self.create_user("alice")

        iro_obj = storage_iro.get_latest_iro("alice")
        payload = storage_iro.decrypt_iro("alice", iro_obj)

        self.assertIsNotNone(iro_obj)
        self.assertEqual(iro_obj["type"], "iro")
        self.assertEqual(payload["owner_pubkey"], alice["pubkey"])
        self.assertIn("object_ids", payload)
        self.assertIn("peer_refs", payload)
        self.assertEqual(
            iro_obj.get("meta", {}).get("encrypted", {}).get("scheme"),
            "x25519-aesgcm-v1",
        )
        self.assertIsNone(iro_obj.get("meta", {}).get("legacy_encrypted"))
        self.assertEqual(alice["key_derivation_version"], 1)
        self.assertEqual(alice["signing_scheme"], "seed-ed25519-v1")
        self.assertEqual(alice["encryption_scheme"], "seed-x25519-v1")
        self.assertTrue(alice["seed_fingerprint"])
        self.assertNotIn("rsa_pubkey", alice)
        self.assertIn(iro_obj["id"], pinned_objects("iro"))

    def test_republished_iro_tracks_new_local_objects(self):
        alice = self.create_user("alice")
        self.create_user("bob")
        service = ChatService()
        rooms = RoomService()

        storage_profile.follow(alice["pubkey"], storage_profile.get_user("bob")["pubkey"])
        service.chat_say("bob", "alice", "hi bob")
        rooms.create_room("lab", "alice", private=False, ttl=None)
        storage_iro.publish_local_iro("alice")

        payload = storage_iro.decrypt_iro("alice")

        self.assertTrue(payload["post_ids"] or payload["object_ids"])
        self.assertTrue(payload["chat_ids"])
        self.assertTrue(payload["room_ids"])

    def test_dm_delivery_round_trip_between_two_users(self):
        self.create_user("alice")
        self.create_user("bob")
        service = ChatService()

        service.chat_say("bob", "alice", "hello bob")

        bob_msgs, _ = service.chat_read_messages("alice", "bob")
        alice_msgs, _ = service.chat_read_messages("bob", "alice")

        self.assertEqual(len(bob_msgs), 1)
        self.assertEqual(bob_msgs[0]["sender"], "alice")
        self.assertEqual(bob_msgs[0]["content"], "hello bob")
        self.assertEqual(len(alice_msgs), 1)
        self.assertEqual(alice_msgs[0]["content"], "hello bob")

    def test_root_seed_derives_stable_signing_and_recovery_material(self):
        self.create_user("alice")

        first_root = crypto_seed.load_or_create_root_seed("alice")
        second_root = crypto_seed.load_or_create_root_seed("alice")
        self.assertEqual(first_root, second_root)

        first_signing_priv, first_signing_pub = crypto_sign.load_or_create_signing_keys("alice")
        second_signing_priv, second_signing_pub = crypto_sign.load_or_create_signing_keys("alice")
        self.assertEqual(
            first_signing_priv.private_bytes_raw(),
            second_signing_priv.private_bytes_raw(),
        )
        self.assertEqual(
            first_signing_pub.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
            second_signing_pub.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
        )

        from storage.crypto import derive_recovery_key

        self.assertEqual(derive_recovery_key("alice"), derive_recovery_key("alice"))

    def test_mnemonic_round_trip_matches_root_seed(self):
        self.create_user("alice")

        root_seed = crypto_seed.load_or_create_root_seed("alice")
        phrase = crypto_mnemonic.seed_to_mnemonic(root_seed)
        recovered_seed = crypto_mnemonic.mnemonic_to_seed(phrase)

        self.assertEqual(root_seed, recovered_seed)
        self.assertEqual(len(phrase.split()), 24)

    def test_legacy_v1_mnemonic_round_trip_still_works(self):
        self.create_user("alice")

        root_seed = crypto_seed.load_or_create_root_seed("alice")
        phrase = crypto_mnemonic.seed_to_mnemonic_v1(root_seed)
        recovered_seed = crypto_mnemonic.mnemonic_to_seed(phrase)

        self.assertEqual(root_seed, recovered_seed)
        self.assertEqual(len(phrase.split()), 56)

    def test_backup_file_round_trip_restores_identity_and_objects(self):
        alice = self.create_user("alice")
        self.create_user("bob")
        service = ChatService()
        rooms = RoomService()

        storage_profile.follow(alice["pubkey"], storage_profile.get_user("bob")["pubkey"])
        service.chat_say("bob", "alice", "from backup flow")
        rooms.create_room("archive", "alice", private=False, ttl=None)
        archive_room_id = rooms.build_room_state("archive")["room_id"]
        storage_iro.publish_local_iro("alice")

        backup_path = self.root / "backup.enc"
        storage_backup.create_backup_file("alice", backup_path, "backup-pass")

        for path in self.objects_dir.glob("*.json"):
            path.unlink()
        for path in self.users_dir.glob("*"):
            path.unlink()
        for path in self.sign_dir.glob("*"):
            path.unlink()
        for path in self.seed_dir.glob("*"):
            path.unlink()
        if self.user_storage_file.exists():
            self.user_storage_file.unlink()

        result = storage_backup.import_backup_file(backup_path, "backup-pass")
        restored_user = storage_profile.get_user("alice")
        restored_payload = storage_iro.decrypt_iro("alice")

        self.assertEqual(result["username"], "alice")
        self.assertTrue(result["has_iro"])
        self.assertEqual(restored_user["pubkey"], alice["pubkey"])
        self.assertEqual(restored_payload["owner_pubkey"], alice["pubkey"])
        self.assertIn(archive_room_id, restored_payload["room_ids"])

    def test_backup_file_omits_rsa_material_for_new_deterministic_identity(self):
        self.create_user("alice")
        backup_path = self.root / "deterministic-only.enc"

        storage_backup.create_backup_file("alice", backup_path, "backup-pass")
        encrypted = json.loads(backup_path.read_text())
        payload = storage_backup._decrypt_payload(encrypted, "backup-pass")

        self.assertNotIn("rsa_private_pem", payload)
        self.assertNotIn("rsa_public_pem", payload)

    def test_backup_file_includes_rsa_material_only_for_legacy_identity(self):
        self.create_user("alice")
        self.enable_legacy_rsa("alice")
        storage_iro.publish_local_iro("alice")
        backup_path = self.root / "legacy-backed.enc"

        storage_backup.create_backup_file("alice", backup_path, "backup-pass")
        encrypted = json.loads(backup_path.read_text())
        payload = storage_backup._decrypt_payload(encrypted, "backup-pass")

        self.assertIn("rsa_private_pem", payload)
        self.assertIn("rsa_public_pem", payload)

    def test_restore_flow_restores_session_and_summary(self):
        alice = self.create_user("alice")
        backup_path = self.root / "restore-flow.enc"
        storage_backup.create_backup_file("alice", backup_path, "restore-pass")

        for path in self.objects_dir.glob("*.json"):
            path.unlink()
        for path in self.users_dir.glob("*"):
            path.unlink()
        for path in self.sign_dir.glob("*"):
            path.unlink()
        for path in self.seed_dir.glob("*"):
            path.unlink()
        if self.user_storage_file.exists():
            self.user_storage_file.unlink()

        result = storage_restore.restore_from_file(
            backup_path,
            "restore-pass",
            auto_login=True,
        )
        session = storage_session.load_session()
        restored_user = storage_profile.get_user("alice")

        self.assertEqual(result["username"], "alice")
        self.assertTrue(result["session_restored"])
        self.assertEqual(session["username"], "alice")
        self.assertEqual(restored_user["pubkey"], alice["pubkey"])
        self.assertIn("object_ids", result["recovery_summary"])

    def test_restore_from_mnemonic_recovers_identity_from_iro(self):
        alice = self.create_user("alice")
        bob = self.create_user("bob")
        self.enable_legacy_rsa("alice")
        self.enable_legacy_rsa("bob")
        alice = storage_profile.get_user("alice")
        bob = storage_profile.get_user("bob")
        service = ChatService()
        legacy_encrypted = encrypt_for_recipients(
            "legacy hello",
            service.recipient_key_map([alice["pubkey"], bob["pubkey"]]),
            preferred_scheme="rsa-oaep-v1",
        )
        legacy_dm = BeepObject.create_object(
            type_="dm",
            author_pubkey=bob["pubkey"],
            content="[encrypted]",
            meta={
                "chat": service.chat_id_from_pubkeys(
                    service.chat_participant_pubkeys("alice", "bob")
                ),
                "encrypted": legacy_encrypted,
            },
        )
        storage_objects.save_object(legacy_dm.to_dict())
        service.chat_say("bob", "alice", "new hello")
        storage_iro.publish_local_iro("alice")
        phrase = storage_backup.create_mnemonic("alice")

        for path in self.users_dir.glob("*"):
            path.unlink()
        for path in self.sign_dir.glob("*"):
            path.unlink()
        for path in self.seed_dir.glob("*"):
            path.unlink()
        if self.user_storage_file.exists():
            self.user_storage_file.unlink()

        result = storage_restore.restore_from_mnemonic(
            phrase,
            local_password="fresh-pass",
            auto_login=True,
        )
        restored_user = storage_profile.get_user("alice")
        restored_payload = storage_iro.decrypt_iro("alice")
        session = storage_session.load_session()
        messages, total = service.chat_read_messages("bob", "alice")

        self.assertEqual(result["username"], "alice")
        self.assertEqual(restored_user["pubkey"], alice["pubkey"])
        self.assertEqual(restored_payload["owner_pubkey"], alice["pubkey"])
        self.assertEqual(session["username"], "alice")
        self.assertFalse(result["legacy_messages_unavailable"])
        self.assertEqual(total, 2)
        self.assertEqual([message["content"] for message in messages], ["legacy hello", "new hello"])

    def test_local_authored_objects_are_auto_pinned_for_retention(self):
        alice = self.create_user("alice")
        obj = BeepObject.create_object(
            type_="post",
            author_pubkey=alice["pubkey"],
            content="hello retention",
        )

        saved = storage_objects.save_object(obj.to_dict())
        self.assertIsNotNone(obj.id)

        self.assertTrue(saved)
        self.assertIn(obj.id, pinned_objects("authored"))

    def test_prune_objects_keeps_local_history_and_removes_unretained_remote_objects(self):
        alice = self.create_user("alice")
        bob = self.create_user("bob")

        alice_post = BeepObject.create_object(
            type_="post",
            author_pubkey=alice["pubkey"],
            content="keep me",
        )
        bob_post = BeepObject.create_object(
            type_="post",
            author_pubkey=bob["pubkey"],
            content="prune me",
        )
        storage_objects.save_object(alice_post.to_dict())
        storage_objects.save_object(bob_post.to_dict())

        users = storage_profile.load_users()
        users.pop("bob")
        storage_profile.save_users(users)

        dry_run = storage_objects.prune_objects(dry_run=True)
        applied = storage_objects.prune_objects(dry_run=False)

        self.assertIn(alice_post.id, dry_run["retained"])
        self.assertIn(bob_post.id, dry_run["prunable"])
        self.assertIsNotNone(storage_objects.get_object(alice_post.id))
        self.assertIsNone(storage_objects.get_object(bob_post.id))
        self.assertIn(bob_post.id, applied["pruned"])

    def test_prune_objects_keeps_followed_remote_author_history(self):
        alice = self.create_user("alice")
        bob = self.create_user("bob")

        storage_profile.follow(alice["pubkey"], bob["pubkey"])
        bob_post = BeepObject.create_object(
            type_="post",
            author_pubkey=bob["pubkey"],
            content="keep because followed",
        )
        storage_objects.save_object(bob_post.to_dict())

        users = storage_profile.load_users()
        users.pop("bob")
        storage_profile.save_users(users)

        report = storage_objects.prune_objects(dry_run=True)
        bob_obj = storage_objects.get_object(bob_post.id)

        self.assertIn(bob_post.id, report["retained"])
        self.assertIsNotNone(bob_obj)
        self.assertEqual(
            storage_objects.retention_reason(bob_obj),
            "following",
        )

    def test_prune_objects_keeps_decryptable_dm_history_for_local_participant(self):
        alice = self.create_user("alice")
        bob = self.create_user("bob")
        service = ChatService()

        service.chat_say("alice", "bob", "hello alice")
        dm_objects = storage_objects.query_objects(obj_type="dm")
        self.assertEqual(len(dm_objects), 1)
        dm_id = dm_objects[0]["id"]

        users = storage_profile.load_users()
        users.pop("bob")
        storage_profile.save_users(users)

        report = storage_objects.prune_objects(dry_run=True)

        self.assertIn(dm_id, report["retained"])
        dm_obj = storage_objects.get_object(dm_id)
        self.assertIsNotNone(dm_obj)
        self.assertEqual(
            storage_objects.retention_reason(dm_obj),
            "chat_participant",
        )

    def test_recovery_sync_uses_iro_peer_refs_and_object_ids(self):
        alice = self.create_user("alice")
        storage_iro.publish_local_iro("alice")
        iro_payload = storage_iro.decrypt_iro("alice")

        target_ids = iro_payload["object_ids"][:2]

        with patch("storage.restore.decrypt_iro", return_value={**iro_payload, "object_ids": target_ids, "peer_refs": ["http://peer-a"]}), patch(
            "storage.restore.recover_objects",
            return_value={
                "owner_pubkey": alice["pubkey"],
                "requested": len(target_ids),
                "imported": len(target_ids),
                "missing": [],
                "types": Counter({"profile": len(target_ids)}),
            },
        ) as mock_recover:
            result = storage_restore.recover_missing_from_iro("alice", verbose=False)

        mock_recover.assert_called_once_with(
            alice["pubkey"],
            target_ids,
            ["http://peer-a"],
            verbose=False,
        )
        self.assertEqual(result["imported"], len(target_ids))
        self.assertEqual(result["peer_count"], 1)

    def test_recovery_sync_falls_back_to_peer_scan_when_local_iro_is_unavailable(self):
        alice = self.create_user("alice")
        fake_iro = storage_iro.get_latest_iro("alice")

        with patch("storage.restore.decrypt_iro", side_effect=[None, {"object_ids": [], "peer_refs": []}]), patch(
            "storage.restore.load_peers", return_value=["http://fallback-peer"]
        ), patch(
            "storage.restore.recover_latest_iro", return_value=fake_iro
        ) as mock_discover, patch(
            "storage.restore.recover_objects",
            return_value={
                "owner_pubkey": alice["pubkey"],
                "requested": 0,
                "imported": 0,
                "missing": [],
                "types": Counter(),
            },
        ):
            result = storage_restore.recover_missing_from_iro("alice", verbose=False)

        mock_discover.assert_called_once_with(
            alice["pubkey"],
            ["http://fallback-peer"],
            verbose=False,
        )
        self.assertEqual(result["peer_count"], 1)
        self.assertGreaterEqual(result["pinned"], 1)

    @patch("network.sync.fetch_object")
    @patch("network.sync.requests.get")
    def test_recover_latest_iro_discovers_newest_peer_iro(self, mock_get, mock_fetch):
        alice = self.create_user("alice")
        older_payload = storage_iro.build_local_iro_payload(alice["pubkey"])
        older_payload["peer_refs"] = ["http://peer-a"]
        older_id = storage_iro.publish_iro(alice["pubkey"], older_payload)
        older = storage_objects.get_object(older_id)

        time.sleep(0.01)
        newer_payload = storage_iro.build_local_iro_payload(alice["pubkey"])
        newer_payload["peer_refs"] = ["http://peer-a", "http://peer-b"]
        newer_id = storage_iro.publish_iro(alice["pubkey"], newer_payload)
        newer = storage_objects.get_object(newer_id)

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"objects": [older_id, newer_id]}
        mock_fetch.side_effect = lambda peer, obj_id: {older_id: older, newer_id: newer}.get(obj_id)

        discovered = network_sync.recover_latest_iro(alice["pubkey"], ["http://peer-a"], verbose=False)

        self.assertEqual(discovered["id"], newer_id)

    def test_private_room_invite_join_message_and_dissolve(self):
        self.create_user("alice")
        self.create_user("bob")
        rooms = RoomService()

        rooms.create_room("lounge", "alice", private=True, ttl=None)
        self.assertEqual(rooms.invite("lounge", "bob", actor="alice"), "invited")
        self.assertEqual(rooms.join_room("lounge", "bob"), "joined")

        rooms.say("lounge", "alice", "private hello")
        bob_msgs, _ = rooms.read_messages("lounge", "bob")

        self.assertEqual(len(bob_msgs), 1)
        self.assertEqual(bob_msgs[0]["sender"], "alice")
        self.assertEqual(bob_msgs[0]["content"], "private hello")

        self.assertEqual(rooms.dissolve_room("lounge", "alice"), "dissolved")
        self.assertIsNone(rooms.build_room_state("lounge"))
        self.assertNotIn("lounge", rooms.list_rooms())

    def test_logout_clears_other_terminal_state_on_refresh(self):
        user = self.create_user("alice")
        storage_session.save_session(user["username"], user["pubkey"])

        state_one = AppState()
        state_two = AppState()

        auth.dispatch("logout", "", state_one)
        status = state_two.refresh_session()

        self.assertEqual(status, "cleared")
        self.assertIsNone(state_two.user)
        self.assertIsNone(state_two.pubkey)

    def test_node_session_watcher_exits_when_session_becomes_invalid(self):
        with patch("network.node.session_matches", return_value=False), patch(
            "network.node.time.sleep", return_value=None
        ), patch("network.node.os._exit", side_effect=SystemExit) as mock_exit:
            with self.assertRaises(SystemExit):
                network_node._watch_session("alice", "pubkey_1")

        mock_exit.assert_called_once_with(0)

    def test_connect_command_resolves_known_handle(self):
        alice = self.create_user("alice")
        state = SimpleNamespace(user="alice", pubkey=alice["pubkey"])

        output = io.StringIO()
        with redirect_stdout(output):
            connect_command.dispatch("connect", "", state)

        self.assertIn(f"alice#{alice['pubkey'][:6]}", output.getvalue())

    def test_presence_endpoint_ignores_stale_presence(self):
        alice = self.create_user("alice")
        presence_id = storage_presence.publish_local_presence(
            "alice",
            "http://127.0.0.1:9001",
            ttl_seconds=1,
        )
        presence = storage_objects.get_object(presence_id)

        self.assertIsNotNone(presence)
        self.assertTrue(storage_presence.is_presence_fresh(presence, now=presence["timestamp"] + 0.5))
        self.assertFalse(storage_presence.is_presence_fresh(presence, now=presence["timestamp"] + 2))

        with patch("storage.presence.time.time", return_value=presence["timestamp"] + 2):
            self.assertIsNone(storage_presence.get_presence_endpoint(alice["pubkey"]))

    def test_presence_uses_configured_public_endpoint_when_set(self):
        alice = self.create_user("alice")
        storage_network_policy.update_network_policy(
            public_endpoint="https://relay.example.net"
        )

        presence_id = storage_presence.publish_local_presence(
            "alice",
            "http://127.0.0.1:9001",
        )
        presence = storage_objects.get_object(presence_id)

        self.assertIsNotNone(presence)
        self.assertEqual(
            presence["meta"].get("endpoint"),
            "https://relay.example.net",
        )
        self.assertEqual(
            storage_presence.get_presence_endpoint(alice["pubkey"]),
            "https://relay.example.net",
        )

    def test_direct_only_strategy_excludes_relays_from_targets(self):
        storage_network_policy.update_network_policy(
            relay_enabled=True,
            strategy="direct-only",
        )
        network_peers.save_peers(["http://peer-a"])
        storage_relay.save_relays(["http://relay-a"])

        targets = storage_relay.load_network_targets()

        self.assertEqual(targets, ["http://peer-a"])

    def test_chat_and_follow_accept_identity_handles(self):
        alice = self.create_user("alice")
        bob = self.create_user("bob")
        bob_handle = f"bob#{bob['pubkey'][:6]}"

        chat_state = AppState()
        chat_state.user = "alice"
        chat_state.pubkey = alice["pubkey"]

        from commands import chat as chat_command
        from commands import follow as follow_command

        chat_output = io.StringIO()
        with redirect_stdout(chat_output):
            chat_command.dispatch("chat", bob_handle, chat_state)

        self.assertEqual(chat_state.current_chat, "bob")
        self.assertIn("Entered chat with bob", chat_output.getvalue())

        follow_output = io.StringIO()
        with redirect_stdout(follow_output):
            follow_command.dispatch("follow", bob_handle, chat_state)

        self.assertIn(
            bob["pubkey"],
            storage_profile.get_effective_following(alice["pubkey"]),
        )
        self.assertIn("now following bob", follow_output.getvalue())

    @patch("network.node_manager._node_is_reachable", return_value=True)
    @patch("network.node_manager.subprocess.Popen")
    @patch("network.node_manager._find_free_port", return_value=9311)
    def test_background_node_manager_starts_and_persists_runtime(
        self,
        mock_port,
        mock_popen,
        mock_reachable,
    ):
        mock_popen.return_value.pid = 4242
        storage_network_policy.update_network_policy(node_autostart=True)

        runtime = network_node_manager.ensure_background_node("alice", "pubkey_1")

        self.assertIsNotNone(runtime)
        self.assertEqual(runtime["port"], 9311)
        self.assertEqual(runtime["pid"], 4242)
        self.assertEqual(
            network_node_manager.load_node_runtime()["url"],
            "http://127.0.0.1:9311",
        )
        mock_popen.assert_called_once()
        mock_port.assert_called_once_with()
        self.assertGreaterEqual(mock_reachable.call_count, 1)

    @patch("network.node_manager._node_is_reachable", return_value=True)
    @patch("network.node_manager.subprocess.Popen")
    def test_background_node_manager_respects_disabled_autostart(
        self,
        mock_popen,
        mock_reachable,
    ):
        storage_network_policy.update_network_policy(node_autostart=False)

        runtime = network_node_manager.ensure_background_node("alice", "pubkey_1")

        self.assertIsNone(runtime)
        mock_popen.assert_not_called()
        mock_reachable.assert_not_called()

    @patch("app.ensure_background_node")
    def test_app_starts_background_node_after_login(self, mock_ensure_node):
        user = self.create_user("alice")
        state = AppState()

        auth.dispatch("login", "-u alice -p pass123", state)
        if state.user and state.pubkey:
            import app

            app.state = state
            app._ensure_background_node_for_session()

        mock_ensure_node.assert_called_once_with("alice", user["pubkey"])


if __name__ == "__main__":
    unittest.main()
