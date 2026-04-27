from core.identity import resolve_username
from storage.objects import query_objects
from storage.profile import get_user, get_effective_followers, get_effective_following


def dispatch(cmd, args, state):
    parts = args.split() if args else []

    show_posts = "--posts" in parts
    show_shared = "--shared" in parts

    username = next((part for part in parts if not part.startswith("--")), None)
    username = username or state.user

    if not username:
        print("[PROFILE] No user selected. Log in or pass a username.")
        return

    profile_data = get_user(username)
    if not profile_data:
        print(f"[PROFILE] User '{username}' not found")
        return

    followers = [resolve_username(pubkey) for pubkey in sorted(get_effective_followers(profile_data["pubkey"]))]
    following = [resolve_username(pubkey) for pubkey in sorted(get_effective_following(profile_data["pubkey"]))]

    authored = query_objects(author=profile_data["pubkey"])
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
