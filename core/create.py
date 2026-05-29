# core/create.py
"""Functions to create new objects like posts, comments, shares, and quotes."""

from typing import Literal, Optional

from core.object import BeepObject
from storage.objects import save_object


PostType = Literal["post", "comment", "share", "quote"]


def create_post(
    author_pubkey: str,
    content: str,
    *,
    post_type: PostType = "post",
    shared_from: Optional[str] = None,
    quote: bool = False,
    parent_id: Optional[str] = None,
) -> str:
    obj = BeepObject.create_object(
        type_=post_type,
        author_pubkey=author_pubkey,
        content=content,
        meta={
            "shared_from": shared_from,
            "quote": quote,
            "parent_id": parent_id,
        },
    )
    save_object(obj.to_dict())
    # return obj.id

    post_id = obj.id
    if post_id is None:
        raise ValueError("Created object has no id")

    return post_id