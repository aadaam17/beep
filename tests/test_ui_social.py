import unittest
from unittest.mock import patch

from ui.screens.home import _build_feed_presentation, _load_profile_cards
from ui.screens.post import PostScreen


class UISocialTests(unittest.TestCase):
    @patch("ui.screens.home.is_following")
    @patch("ui.screens.home.get_known_users")
    @patch("ui.screens.home.query_objects")
    @patch("ui.screens.home.get_effective_following")
    @patch("ui.screens.home.get_effective_followers")
    @patch("ui.screens.home.get_user")
    @patch("ui.screens.home.load_session")
    def test_profile_cards_include_followable_known_users(
        self,
        mock_load_session,
        mock_get_user,
        mock_get_followers,
        mock_get_following,
        mock_query_objects,
        mock_get_known_users,
        mock_is_following,
    ):
        mock_load_session.return_value = {"username": "alice", "pubkey": "a" * 64}
        mock_get_user.return_value = {"username": "alice", "pubkey": "a" * 64}
        mock_get_followers.side_effect = [set(), set()]
        mock_get_following.side_effect = [set(), set()]
        mock_query_objects.return_value = []
        mock_get_known_users.return_value = [
            {"username": "alice", "pubkey": "a" * 64},
            {"username": "bob", "pubkey": "b" * 64},
        ]
        mock_is_following.return_value = False

        cards = _load_profile_cards()

        followable_cards = [card for card in cards if card.followable]
        self.assertEqual(len(followable_cards), 1)
        self.assertEqual(followable_cards[0].target_username, "bob")
        self.assertIn("Press `f`", "\n".join(followable_cards[0].details))

    def test_post_screen_bindings_include_social_actions(self):
        keys = {binding.key for binding in PostScreen.BINDINGS}

        self.assertIn("c", keys)
        self.assertIn("q", keys)
        self.assertIn("s", keys)

    @patch("ui.screens.home.resolve_username", return_value="alice")
    @patch("ui.screens.home.get_object")
    def test_feed_presentation_for_quote_shows_original_context(
        self,
        mock_get_object,
        mock_resolve_username,
    ):
        mock_get_object.return_value = {
            "id": "source-1",
            "type": "post",
            "author": "a" * 64,
            "content": "Original source post",
            "timestamp": 1.0,
            "meta": {},
            "signature": "sig",
        }
        quote = {
            "id": "quote-1",
            "type": "quote",
            "author": "b" * 64,
            "content": "My take on this",
            "timestamp": 2.0,
            "meta": {"shared_from": "source-1", "quote": True},
            "signature": "sig",
        }

        headline, preview, context_lines = _build_feed_presentation(quote)

        self.assertEqual(headline, "Quoted @alice")
        self.assertEqual(preview, "My take on this")
        self.assertIn("Original post:", context_lines)
        self.assertIn("Original source post", context_lines)


if __name__ == "__main__":
    unittest.main()
