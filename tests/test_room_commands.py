import unittest
from types import SimpleNamespace
from unittest.mock import patch

from commands.room import EPHEMERAL_TTL_SECONDS, _parse_ephemeral_ttl
from commands.room import dispatch as room_dispatch
from state import Mode


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

    @patch("commands.room.fs.leave_room", side_effect=ValueError("Room not found"))
    def test_leave_exits_context_when_ephemeral_room_expired(self, mock_leave_room):
        state = SimpleNamespace(
            mode=Mode.ROOM,
            current_room="short_room",
            user="alice",
            exit_room=lambda: setattr(state, "mode", Mode.GLOBAL_FYP),
        )

        room_dispatch("leave", "", state)

        mock_leave_room.assert_called_once_with("short_room", "alice")
        self.assertEqual(state.mode, Mode.GLOBAL_FYP)


if __name__ == "__main__":
    unittest.main()
