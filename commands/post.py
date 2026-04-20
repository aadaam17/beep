# commands/post.py

from storage.profile import get_user

from core.create import create_post
from storage.objects import get_object


def dispatch(cmd, args, state):
    user = state.user
    if not user:
        print("[POST] You must be logged in to post")
        return

    parts = args.split() if args else []

    # Make sure the user exists
    if not get_user(user):
        print(f"[POST] Error: user '{user}' does not exist")
        return

    if cmd == "post":
        content = args.strip()
        if not content:
            print("[POST] Cannot create empty post")
            return
        
        post_id = create_post(state.pubkey, content)
        print(f"[POST] Post created: {post_id}")

    elif cmd == "comment":
        if len(parts) < 2:
            print("[COMMENT] Usage: comment <post_id> <content>")
            return
        post_id, content = parts[0], " ".join(parts[1:])
        parent = get_object(post_id)
        if not parent:
            print(f"[COMMENT] Error: Post {post_id} does not exist or was deleted")
            return
        comment_id = create_post(state.pubkey, content, post_type="comment", parent_id=post_id)
        print(f"[COMMENT] Comment added: {comment_id} (to {post_id})")

    elif cmd == "share":
        if not parts:
            print("[SHARE] Usage: share <post_id>")
            return
        pid = parts[0]
        parent = get_object(pid)
        if not parent:
            print(f"[SHARE] Error: Post {pid} does not exist or was deleted")
            return
        shared_id = create_post(state.pubkey, parent["content"], post_type="share", shared_from=pid)
        print(f"[SHARE] Shared post: {shared_id}")

    elif cmd == "quote":
        if len(parts) < 2:
            print("[QUOTE] Usage: quote <post_id> <content>")
            return
        pid, content = parts[0], " ".join(parts[1:])
        parent = get_object(pid)
        if not parent:
            print(f"[QUOTE] Error: Post {pid} does not exist or was deleted")
            return
        quote_id = create_post(state.pubkey, content, post_type="quote", shared_from=pid, quote=True)
        print(f"[QUOTE] Quote created: {quote_id} (from {pid})")

    elif cmd == "delete":
        print("[DELETE] Delete is not supported for immutable objects yet.")
