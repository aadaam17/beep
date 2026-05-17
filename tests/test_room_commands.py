import unittest

from commands.room import EPHEMERAL_TTL_SECONDS, _parse_ephemeral_ttl


class RoomCommandTests(unittest.TestCase):
    def test_ephemeral_defaults_to_24_hours_when_no_duration_is_supplied(self):
        ttl = _parse_ephemeral_ttl(["ephe_room", "--ephemeral"])

        self.assertEqual(ttl, EPHEMERAL_TTL_SECONDS)

    def test_ephemeral_supports_explicit_units(self):
        self.assertEqual(_parse_ephemeral_ttl(["ephe_room", "--ephemeral", "15s"]), 15)
        self.assertEqual(_parse_ephemeral_ttl(["ephe_room", "--ephemeral", "1m"]), 60)
        self.assertEqual(_parse_ephemeral_ttl(["ephe_room", "--ephemeral", "3h"]), 10800)
        self.assertEqual(_parse_ephemeral_ttl(["ephe_room", "--ephemeral", "2d"]), 172800)

    def test_ephemeral_supports_raw_seconds(self):
        self.assertEqual(
            _parse_ephemeral_ttl(["ephe_room", "--ephemeral", "25762382"]),
            25762382,
        )

    def test_ephemeral_rejects_invalid_units(self):
        with self.assertRaises(ValueError):
            _parse_ephemeral_ttl(["ephe_room", "--ephemeral", "7w"])


if __name__ == "__main__":
    unittest.main()
