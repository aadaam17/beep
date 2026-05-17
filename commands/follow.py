# commands/follow.py

from typing import Callable

from core.types import CommandState, UserRecord

from storage.profile import (
    follow,
    unfollow,
    get_user,
    get_effective_following,
    is_following,
)
def dispatch(cmd: str, args: str, state: CommandState) -> None:
    args_list = args.strip().split()

    actor_pubkey = state.pubkey
    if actor_pubkey is None:
        print(f"[{cmd.upper()}] You must log in first")
        return

    if not args_list:
        print(f"[{cmd.upper()}] Usage: {cmd} <username>")
        return

    target_username = args_list[0].lower()
    target_profile: UserRecord | None = get_user(target_username)

    # ---------------------------
    # VALIDATION
    # ---------------------------
    if not target_profile:
        print(f"[{cmd.upper()}] User '{target_username}' does not exist")
        return

    target_pubkey: str = target_profile["pubkey"]

    # Prevent self-follow/unfollow
    if target_pubkey == actor_pubkey:
        print(f"[{cmd.upper()}] You cannot {cmd} yourself")
        return

    # ---------------------------
    # ACTION
    # ---------------------------
    action: Callable[[str, str], None] = follow if cmd == "follow" else unfollow

    try:
        already_following = is_following(actor_pubkey, target_pubkey)

        if cmd == "follow" and already_following:
            print(f"[{cmd.upper()}] You are already following {target_username}")
            return

        if cmd == "unfollow" and not already_following:
            print(f"[{cmd.upper()}] You are not following {target_username}")
            return

        action(actor_pubkey, target_pubkey)

        verb = "now following" if cmd == "follow" else "unfollowed"
        following_count = len(get_effective_following(actor_pubkey))

        print(f"[{cmd.upper()}] You {verb} {target_username}")
        print(f"[{cmd.upper()}] You now follow {following_count} users")

    except ValueError as e:
        print(f"[{cmd.upper()}] Error: {e}")
