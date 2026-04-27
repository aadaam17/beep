from datetime import datetime

from core.feed import get_all_posts, get_followed_posts
from core.identity import resolve_username
from storage.objects import query_objects
from storage.profile import get_effective_following

POSTS_PER_PAGE = 15


def relative_time(timestamp):
    try:
        past = datetime.fromtimestamp(int(timestamp))
    except (TypeError, ValueError, OSError):
        return ""

    now = datetime.now()
    diff = now - past
    seconds = max(int(diff.total_seconds()), 0)

    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"

def _print_comments(post_id):
    comments = [
        obj for obj in query_objects(obj_type="comment")
        if obj.get("meta", {}).get("parent_id") == post_id
    ]

    for comment in comments:
        author = resolve_username(comment["author"])
        rel = relative_time(comment["timestamp"])
        print(f"    : [{rel}] [{author}] - {comment['id']}: {comment['content']}")


def _print_posts(posts, state):
    for obj in posts:
        author = resolve_username(obj["author"])
        ts = datetime.fromtimestamp(obj["timestamp"]).strftime("%d.%m.%Y")
        rel = relative_time(obj["timestamp"])
        meta = obj.get("meta", {})

        if meta.get("shared_from"):
            label = "Quoted" if meta.get("quote") else "Shared"
            content_suffix = f": {obj['content']}" if meta.get("quote") else ""
            print(f":: {label} [{ts} | {rel}] [{author}] - {obj['id']}{content_suffix}")

            original = next(
                (candidate for candidate in query_objects() if candidate["id"] == meta["shared_from"]),
                None,
            )
            if original:
                original_author = resolve_username(original["author"])
                original_rel = relative_time(original["timestamp"])
                original_ts = datetime.fromtimestamp(original["timestamp"]).strftime("%d.%m.%Y")
                print(
                    f"      -> [{original_ts} | {original_rel}] "
                    f"[{original_author}] - {original['id']}: {original['content']}"
                )
        else:
            print(f":: [{ts} | {rel}] [{author}] - {obj['id']}: {obj['content']}")

        _print_comments(obj["id"])
        print()


def dispatch(cmd, args, state):
    if not hasattr(state, "fyp_index"):
        state.fyp_index = 0

    if cmd == "fyp":
        fyp_type = (args or "global").strip()
        state.switch_fyp(fyp_type)
        state.fyp_index = 0
        _print_posts(_get_current_feed(state), state)
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
        _print_posts(posts, state)
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
