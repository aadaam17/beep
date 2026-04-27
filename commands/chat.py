from storage.fs import BeepFS
from datetime import datetime
from state import Mode

fs = BeepFS()
DEFAULT_READ = 10


def dispatch(cmd, args, state):
    parts = args.split() if args else []
    user = state.user

    if not user:
        print(f"Error: You must be logged in to use '{cmd}'")
        return

    # ================= CHAT =================
    if cmd == "chat":

        # -------- LIST MY CHATS --------
        if not parts:
            chats = fs.list_chats(user)

            if not chats:
                print("No chats.")
                return

            print("Chats:")
            for chat_peer in chats:
                print(f" - {chat_peer}")
            return

        target = parts[0]

        # No self-chat
        if target == user:
            print("Error: You cannot chat with yourself")
            return

        # Target must exist
        if not fs.user_exists(target):
            print(f"Error: User '{target}' does not exist")
            return

        try:
            fs.create_chat(None, user, target)
        except ValueError as e:
            print(f"Error: {e}")
            return

        state.enter_chat(target)
        print(f"Entered chat with {target}")

    # ================= SAY =================
    elif cmd == "say":
        if state.mode != Mode.CHAT:
            print("Error: 'say' can only be used inside a chat")
            return
        if not args:
            print("Error: message required")
            return

        try:
            fs.chat_say(state.current_chat, user, args)
            print("✓ message sent")
        except PermissionError as e:
            print(f"Error: {e}")

    # ================= READ =================
    elif cmd == "read":
        if state.mode != Mode.CHAT:
            print("Error: 'read' can only be used inside a chat")
            return

        num = DEFAULT_READ
        show_all = False

        if parts:
            if parts[0] == "--all":
                show_all = True
            elif parts[0].isdigit():
                num = int(parts[0])

        msgs, _ = fs.chat_read_messages(state.current_chat, user)
        if not msgs:
            print("No messages yet.")
            return

        display = msgs if show_all else msgs[-num:]
        display.sort(key=lambda m: m["timestamp"])

        for m in display:
            t = datetime.fromtimestamp(m["timestamp"]).strftime("%H:%M")
            print(f"[{t}] {m['sender']}: {m['content']}")

    # ================= EXIT =================
    elif cmd == "exit":
        if state.mode != Mode.CHAT:
            print("Error: Not in a chat")
            return

        print("Left chat")
        state.exit_chat()

    else:
        print(f"Unknown chat command: {cmd}")
