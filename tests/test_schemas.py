import unittest

from core.schemas import validate_object_schema
from core.verify import _protocol_is_supported, verify_object


class SchemaValidationTests(unittest.TestCase):
    def test_comment_requires_parent_id(self):
        obj = {
            "id": "abc",
            "type": "comment",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "reply",
            "signature": "11" * 64,
            "meta": {},
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.parent_id is required", errors)

    def test_room_message_requires_encrypted_envelope(self):
        obj = {
            "id": "abc",
            "type": "room_message",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "[encrypted]",
            "signature": "11" * 64,
            "meta": {"room": "room_1"},
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.encrypted is required", errors)

    def test_presence_requires_endpoint_metadata(self):
        obj = {
            "id": "abc",
            "type": "presence",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "alice",
            "signature": "11" * 64,
            "meta": {"username": "alice"},
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.endpoint is required", errors)
        self.assertIn("meta.reachable_via is required", errors)

    def test_tombstone_requires_target_metadata(self):
        obj = {
            "id": "abc",
            "type": "tombstone",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "[deleted]",
            "signature": "11" * 64,
            "meta": {"target": "post_1"},
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.target_type is required", errors)
        self.assertIn("meta.reason is required", errors)

    def test_key_revocation_requires_rotation_metadata(self):
        obj = {
            "id": "abc",
            "type": "key_revocation",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "rotate",
            "signature": "11" * 64,
            "meta": {"action": "rotate", "key_scope": "encryption"},
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.old_key_id is required", errors)
        self.assertIn("meta.new_key_id is required", errors)

    def test_presence_ttl_must_be_integer(self):
        obj = {
            "id": "abc",
            "type": "presence",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "alice",
            "signature": "11" * 64,
            "meta": {
                "username": "alice",
                "endpoint": "http://127.0.0.1:9911",
                "reachable_via": "direct",
                "ttl": "bad",
            },
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.ttl must be int", errors)

    def test_iro_requires_owner_and_recovery_or_rsa_payload(self):
        obj = {
            "id": "abc",
            "type": "iro",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "[encrypted]",
            "signature": "11" * 64,
            "meta": {"version": 1, "payload_kind": "iro_index"},
        }

        errors = validate_object_schema(obj)

        self.assertIn("meta.owner_pubkey is required", errors)
        self.assertIn(
            "meta.encrypted or meta.recovery_encrypted is required",
            errors,
        )

    def test_verify_object_rejects_schema_invalid_follow_before_signature_check(self):
        obj = {
            "id": "abc",
            "type": "follow",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "follow",
            "signature": "11" * 64,
            "meta": {"target": "peer_pubkey"},
        }

        self.assertFalse(verify_object(obj))

    def test_protocol_metadata_accepts_legacy_unversioned_objects(self):
        obj = {
            "id": "abc",
            "type": "post",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "hello",
            "signature": "11" * 64,
            "meta": {},
        }

        self.assertTrue(_protocol_is_supported(obj))

    def test_protocol_metadata_rejects_unsupported_versions(self):
        obj = {
            "id": "abc",
            "type": "post",
            "author": "00" * 32,
            "timestamp": 1,
            "content": "hello",
            "signature": "11" * 64,
            "meta": {"protocol": "beep-object-v1", "protocol_version": 999},
        }

        self.assertFalse(_protocol_is_supported(obj))


if __name__ == "__main__":
    unittest.main()
