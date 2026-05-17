import unittest

from core.schemas import validate_object_schema
from core.verify import verify_object


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


if __name__ == "__main__":
    unittest.main()
