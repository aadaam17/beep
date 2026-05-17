import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from core import thread_view


ROOT = {
    "id": "post_1",
    "type": "post",
    "author": "author_root",
    "timestamp": 1,
    "content": "Root post",
    "meta": {},
}
COMMENT_A = {
    "id": "comment_a",
    "type": "comment",
    "author": "author_a",
    "timestamp": 2,
    "content": "First reply",
    "meta": {"parent_id": "post_1"},
}
COMMENT_B = {
    "id": "comment_b",
    "type": "comment",
    "author": "author_b",
    "timestamp": 3,
    "content": "Reply to first reply",
    "meta": {"parent_id": "comment_a"},
}
COMMENT_C = {
    "id": "comment_c",
    "type": "comment",
    "author": "author_c",
    "timestamp": 4,
    "content": "Sibling reply",
    "meta": {"parent_id": "post_1"},
}


class ThreadViewTests(unittest.TestCase):
    def _fake_get_object(self, obj_id):
        objects = {obj["id"]: obj for obj in [ROOT, COMMENT_A, COMMENT_B, COMMENT_C]}
        return objects.get(obj_id)

    def _fake_query_objects(self, obj_type=None, author=None):
        objects = [ROOT, COMMENT_A, COMMENT_B, COMMENT_C]
        if obj_type:
            objects = [obj for obj in objects if obj["type"] == obj_type]
        if author:
            objects = [obj for obj in objects if obj["author"] == author]
        return list(objects)

    @patch("core.thread_view.resolve_username", side_effect=lambda pubkey: pubkey)
    @patch("core.thread_view.query_objects")
    @patch("core.thread_view.get_object")
    def test_print_thread_renders_nested_comments(self, mock_get_object, mock_query_objects, _resolve):
        mock_get_object.side_effect = self._fake_get_object
        mock_query_objects.side_effect = self._fake_query_objects

        output = io.StringIO()
        with redirect_stdout(output):
            thread_view.print_thread("post_1")

        rendered = output.getvalue()
        self.assertIn("Root post", rendered)
        self.assertIn("First reply", rendered)
        self.assertIn("Reply to first reply", rendered)
        self.assertIn("Sibling reply", rendered)
        self.assertIn("    : [", rendered)
        self.assertIn("        : [", rendered)

    @patch("core.thread_view.resolve_username", side_effect=lambda pubkey: pubkey)
    @patch("core.thread_view.query_objects")
    @patch("core.thread_view.get_object")
    def test_print_focus_view_shows_ancestor_chain_for_comment(self, mock_get_object, mock_query_objects, _resolve):
        mock_get_object.side_effect = self._fake_get_object
        mock_query_objects.side_effect = self._fake_query_objects

        output = io.StringIO()
        with redirect_stdout(output):
            thread_view.print_focus_view("comment_b")

        rendered = output.getvalue()
        self.assertIn("Root post", rendered)
        self.assertIn("First reply", rendered)
        self.assertIn("Reply to first reply", rendered)
        self.assertNotIn("Sibling reply", rendered)


if __name__ == "__main__":
    unittest.main()
