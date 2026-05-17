# core/feed.py

from storage.objects import list_objects, get_object
from core.types import BeepObjectRecord


def get_all_posts() -> list[BeepObjectRecord]:
    """
    Return all feed objects sorted by timestamp DESC.
    """
    posts: list[BeepObjectRecord] = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if not obj:
            continue

        if obj.get("type") in {"post", "share", "quote"}:
            posts.append(obj)

    posts.sort(key=lambda x: x["timestamp"], reverse=True)
    return posts


def get_followed_posts(
    following_pubkeys: set[str],
) -> list[BeepObjectRecord]:
    posts: list[BeepObjectRecord] = []

    for obj_id in list_objects():
        obj = get_object(obj_id)
        if not obj:
            continue

        if (
            obj.get("type") in {"post", "share", "quote"}
            and obj.get("author") in following_pubkeys
        ):
            posts.append(obj)

    posts.sort(key=lambda x: x["timestamp"], reverse=True)
    return posts