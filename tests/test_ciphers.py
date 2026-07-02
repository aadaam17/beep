import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import ciphers


class CipherProfileTests(unittest.TestCase):
    def test_profile_encode_decode_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(ciphers, "CIPHER_DIR", Path(tmpdir)):
                ciphers.create_profile("ops")
                ciphers.set_mapping("ops", "meet tonight", "X91")
                ciphers.set_mapping("ops", "safehouse", "T77")

                encoded, profile = ciphers.encode_text(
                    "meet tonight at safehouse",
                    "ops",
                )
                decoded, ok = ciphers.decode_text(encoded, "ops", profile["version"])

        self.assertEqual(encoded, "X91 at T77")
        self.assertTrue(ok)
        self.assertEqual(decoded, "meet tonight at safehouse")

    def test_export_import_verifies_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "store"
            exported = Path(tmpdir) / "ops.beepcipher"
            imported_store = Path(tmpdir) / "imported"

            with patch.object(ciphers, "CIPHER_DIR", store):
                ciphers.create_profile("ops")
                ciphers.set_mapping("ops", "abort", "R44")
                ciphers.export_profile("ops", exported)

            with patch.object(ciphers, "CIPHER_DIR", imported_store):
                imported = ciphers.import_profile(exported)

        self.assertEqual(imported["profile"], "ops")
        self.assertEqual(imported["mapping"], {"abort": "R44"})
        self.assertTrue(imported["fingerprint"].startswith("sha256:"))

    def test_rotate_and_revoke_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(ciphers, "CIPHER_DIR", Path(tmpdir)):
                ciphers.create_profile("ops")
                ciphers.set_mapping("ops", "safehouse", "T77")
                rotated = ciphers.rotate_profile("ops")
                revoked = ciphers.revoke_profile("ops", rotated["version"])

                with self.assertRaises(PermissionError):
                    ciphers.encode_text("safehouse", "ops")

        self.assertEqual(rotated["version"], 2)
        self.assertEqual(revoked["status"], "revoked")


if __name__ == "__main__":
    unittest.main()
