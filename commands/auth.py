import shlex
import getpass
from storage import profile
from storage.session import save_session, clear_session

def dispatch(cmd, args, state):
    parts = shlex.split(args)
    username = None
    password = None

    # Parse flags
    i = 0
    while i < len(parts):
        if parts[i] in ("-u", "--username"):
            i += 1
            if i < len(parts):
                username = parts[i]
        elif parts[i] in ("-p", "--password"):
            i += 1
            if i < len(parts):
                password = parts[i]
        i += 1

    # Interactive password if not supplied
    if password is None and cmd in ("register", "login"):
        password = getpass.getpass("Enter password: ")

    try:
        if cmd == "register":
            if not username:
                print("[AUTH] Error: Username required! Use -u <username>")
                return

            username_clean = username.lower()  # lowercase for storage
            user = profile.create_user(username_clean, password)
            state.user = user["username"]
            state.pubkey = user["pubkey"]
            save_session(state.user, state.pubkey)
            print(f"[AUTH] User '{username_clean}' registered successfully!")

        elif cmd == "login":
            if not username:
                print("[AUTH] Error: Username required! Use -u <username>")
                return

            username_clean = username.lower()  # lowercase for lookup
            user = profile.authenticate(username_clean, password)
            user = profile.update_user(user["username"], user)
            state.user = user["username"]
            state.pubkey = user["pubkey"]
            save_session(state.user, state.pubkey)
            print(f"[AUTH] User '{username_clean}' logged in successfully!")

        elif cmd == "logout":
            if state.user:
                print(f"[AUTH] User '{state.user}' logged out.")
                state.user = None
                state.pubkey = None
                state.exit_chat()
                state.exit_room()
                state.exit_profile()
                clear_session()
            else:
                print("[AUTH] No user currently logged in.")

    except ValueError as e:
        print(f"[AUTH] Error: {e}")
