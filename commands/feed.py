from core.feed import get_all_posts, get_followed_posts
from core.thread_view import print_thread
from storage.profile import get_effective_following

POSTS_PER_PAGE = 15


def dispatch(cmd, args, state):
    if not hasattr(state, "fyp_index"):
        state.fyp_index = 0

    if cmd == "fyp":
        fyp_type = (args or "global").strip()
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


def _print_posts(posts):
    for obj in posts:
        print_thread(obj["id"])
        print()


def _get_current_feed(state):
    start = getattr(state, "fyp_index", 0)
    end = start + POSTS_PER_PAGE

    if getattr(state, "fyp_type", "global") == "followed":
        if not state.user:
            print("[FYP] Login required. Showing global.")
            posts = get_all_posts()
        else:
            following = get_effective_following(state.pubkey)
            posts = get_followed_posts(following)
    else:
        posts = get_all_posts()

    return posts[start:end]
