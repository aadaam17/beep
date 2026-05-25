"""Profile viewing commands."""

from core.identity import build_identity_handle, find_identity_matches, resolve_username
from core.types import CommandState
from storage.objects import query_objects
from storage.profile import get_effective_followers, get_effective_following


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    parts = args.split() if args else []

    show_posts = "--posts" in parts
    show_shared = "--shared" in parts

    requested_identity = next((part for part in parts if not part.startswith("--")), None)

    if requested_identity is None:
        requested_identity = state.user

    if not requested_identity:
        print("[PROFILE] No user selected. Log in or pass a username.")
        return

    matches = find_identity_matches(requested_identity)
    if not matches:
        print(f"[PROFILE] User '{requested_identity}' not found")
        return
    if len(matches) > 1:
        print(f"[PROFILE] '{requested_identity}' is ambiguous. Use a handle:")
        for match in matches:
            print(f" - {build_identity_handle(match['username'], match['pubkey'])}")
        return

    profile_data = matches[0]
    username = profile_data["username"]
    profile_pubkey: str = profile_data["pubkey"]

    followers = [
        resolve_username(pubkey)
        for pubkey in sorted(get_effective_followers(profile_pubkey))
    ]

    following = [
        resolve_username(pubkey)
        for pubkey in sorted(get_effective_following(profile_pubkey))
    ]

    authored = query_objects(author=profile_pubkey)

    posts = [obj for obj in authored if obj["type"] == "post"]
    shared = [obj for obj in authored if obj["type"] in {"share", "quote"}]

    print(f"\nProfile: {username}")
    print(f"Followers: {len(followers)}")
    print(f"Following: {len(following)}")
    print(f"Posts: {len(posts)}")
    print(f"Shared: {len(shared)}")

    if "--followers" in parts and followers:
        print("Follower list:")
        for follower in followers:
            print(f" - {follower}")

    if "--following" in parts and following:
        print("Following list:")
        for followed in following:
            print(f" - {followed}")

    if show_posts:
        print("\nPosts:")
        if not posts:
            print("  No posts yet.")
        else:
            for obj in posts:
                print(f" - {obj['id']}: {obj['content']}")

    if show_shared:
        print("\nShared posts:")
        if not shared:
            print("  No shared posts yet.")
        else:
            for obj in shared:
                print(f" - {obj['id']}: {obj['content']}")

    print()
