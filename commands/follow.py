from storage.profile import follow, unfollow, get_user


def dispatch(cmd, args, state):
    args = args.strip().split()

    if not state.pubkey:
        print(f"[{cmd.upper()}] You must log in first")
        return

    if not args:
        print(f"[{cmd.upper()}] Usage: {cmd} <username>")
        return

    target_username = args[0].lower()
    target_profile = get_user(target_username)

    # ---------------------------
    # VALIDATION
    # ---------------------------
    if not target_profile:
        print(f"[{cmd.upper()}] User '{target_username}' does not exist")
        return

    target_pubkey = target_profile["pubkey"]

    # Prevent self-follow/unfollow (pubkey-based)
    if target_pubkey == state.pubkey:
        print(f"[{cmd.upper()}] You cannot {cmd} yourself")
        return

    # ---------------------------
    # ACTION
    # ---------------------------
    action = follow if cmd == "follow" else unfollow

    try:
        action(state.pubkey, target_pubkey)

        # load updated profile (still indexed by username locally)
        my_profile = get_user(state.user)

        verb = "now following" if cmd == "follow" else "unfollowed"

        print(f"[{cmd.upper()}] You {verb} {target_username}")
        print(f"[{cmd.upper()}] You now follow {len(my_profile['following'])} users")

    except ValueError as e:
        print(f"[{cmd.upper()}] Error: {e}")