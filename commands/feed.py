# commands/feed.py
"""Feed-related CLI commands."""

from __future__ import annotations

from typing import Protocol, cast

from core.feed import get_all_posts, get_followed_posts
from core.thread_view import print_thread
from core.types import BeepObjectRecord
from state import FeedKind
from storage.profile import get_effective_following

POSTS_PER_PAGE = 15


class FeedState(Protocol):
    user: str | None
    pubkey: str | None

    fyp_index: int
    fyp_type: FeedKind
    hold: bool

    def switch_fyp(self, feed_type: FeedKind) -> None: ...
    def toggle_hold(self) -> bool: ...


def dispatch(cmd: str, args: str, state: FeedState) -> None:
    if not hasattr(state, "fyp_index"):
        state.fyp_index = 0

    if cmd == "fyp":
        requested_feed = (args or "global").strip()
        if requested_feed not in {"global", "followed"}:
            print("[FYP] Usage: fyp global | fyp followed")
            return
        fyp_type = cast(FeedKind, requested_feed)
        state.switch_fyp(fyp_type)
        state.fyp_index = 0
        _print_posts(_get_current_feed(state))
        return

    if cmd == "next":
        if state.hold:
            print("[FYP] Feed is on hold. Use 'resume' to continue.")
            return

        state.fyp_index += POSTS_PER_PAGE
        posts = _get_current_feed(state)

        if not posts:
            print("[FYP] No more posts.")
            state.fyp_index -= POSTS_PER_PAGE
            return

        _print_posts(posts)
        return

    if cmd == "hold":
        state.toggle_hold()
        print(f"[FYP] Feed hold: {state.hold}")
        return

    if cmd == "resume":
        if not state.hold:
            print("[FYP] Feed is not on hold.")
            return

        state.toggle_hold()
        print("[FYP] Feed resumed")


def _print_posts(posts: list[BeepObjectRecord]) -> None:
    for obj in posts:
        print_thread(obj["id"])
        print()


def _get_current_feed(state: FeedState) -> list[BeepObjectRecord]:
    start = state.fyp_index
    end = start + POSTS_PER_PAGE

    posts: list[BeepObjectRecord]

    if state.fyp_type == "followed":
        if not state.user:
            print("[FYP] Login required. Showing global.")
            posts = get_all_posts()
        else:
            following = get_effective_following(state.pubkey or "")
            posts = get_followed_posts(following)
    else:
        posts = get_all_posts()

    return posts[start:end]
