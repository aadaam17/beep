# commands/follow.py

from typing import Callable

from core.identity import build_identity_handle, find_identity_matches
from core.types import CommandState, UserRecord

from storage.profile import (
    follow,
    unfollow,
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
        print(f"[{cmd.upper()}] Usage: {cmd} <username-or-handle>")
        return

    target_identifier = args_list[0].lower()
    matches = find_identity_matches(target_identifier)

    # ---------------------------
    # VALIDATION
    # ---------------------------
    if not matches:
        print(f"[{cmd.upper()}] User '{target_identifier}' is not known locally")
        return
    if len(matches) > 1:
        print(f"[{cmd.upper()}] '{target_identifier}' is ambiguous. Use a handle:")
        for match in matches:
            print(f" - {build_identity_handle(match['username'], match['pubkey'])}")
        return

    target_profile: UserRecord = matches[0]
    target_username = target_profile["username"]

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
