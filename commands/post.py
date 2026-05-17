# commands/post.py

from storage.profile import get_user
from core.create import create_post
from storage.objects import get_object
from state import AppState


def dispatch(cmd: str, args: str, state: AppState) -> None:
    user: str | None = state.user

    if not user:
        print("[POST] You must be logged in to post")
        return

    if not get_user(user):
        print(f"[POST] Error: user '{user}' does not exist")
        return

    parts = args.split() if args else []

    # -------------------
    # POST
    # -------------------
    if cmd == "post":
        content = args.strip()
        if not content:
            print("[POST] Cannot create empty post")
            return

        if not state.pubkey:
            print("[POST] Missing pubkey in state")
            return

        post_id = create_post(state.pubkey, content)
        print(f"[POST] Post created: {post_id}")

    # -------------------
    # COMMENT
    # -------------------
    elif cmd == "comment":
        if len(parts) < 2:
            print("[COMMENT] Usage: comment <object_id> <content>")
            return

        post_id, content = parts[0], " ".join(parts[1:])
        parent = get_object(post_id)

        if not parent:
            print(f"[COMMENT] Error: Object {post_id} does not exist or was deleted")
            return

        if not state.pubkey:
            print("[COMMENT] Missing pubkey in state")
            return

        comment_id = create_post(
            state.pubkey,
            content,
            post_type="comment",
            parent_id=post_id,
        )
        print(f"[COMMENT] Comment added: {comment_id} (to {post_id})")

    # -------------------
    # SHARE
    # -------------------
    elif cmd == "share":
        if not parts:
            print("[SHARE] Usage: share <post_id>")
            return

        pid = parts[0]
        parent = get_object(pid)

        if not parent:
            print(f"[SHARE] Error: Post {pid} does not exist or was deleted")
            return

        if not state.pubkey:
            print("[SHARE] Missing pubkey in state")
            return

        shared_id = create_post(
            state.pubkey,
            parent["content"],
            post_type="share",
            shared_from=pid,
        )
        print(f"[SHARE] Shared post: {shared_id}")

    # -------------------
    # QUOTE
    # -------------------
    elif cmd == "quote":
        if len(parts) < 2:
            print("[QUOTE] Usage: quote <post_id> <content>")
            return

        pid, content = parts[0], " ".join(parts[1:])
        parent = get_object(pid)

        if not parent:
            print(f"[QUOTE] Error: Post {pid} does not exist or was deleted")
            return

        if not state.pubkey:
            print("[QUOTE] Missing pubkey in state")
            return

        quote_id = create_post(
            state.pubkey,
            content,
            post_type="quote",
            shared_from=pid,
            quote=True,
        )
        print(f"[QUOTE] Quote created: {quote_id} (from {pid})")

    elif cmd == "delete":
        print("[DELETE] Delete is not supported for immutable objects yet.")