import shlex
from state import AppState, Mode
from commands import auth, feed, post, profile, follow, chat, room, moderation, help, sync, node
from commands.sync import SyncCommand

from network.peers import add_peer, load_peers, remove_peer
from network.sync import sync
from network.node import run_node

state = AppState()

# Mapping commands to their dispatch modules
COMMAND_MODULES = {
    "auth": ["register", "login", "logout"],
    "post": ["post", "comment", "share", "quote", "delete"],
    "profile": ["profile"],
    "follow": ["follow", "unfollow"],
    "chat": ["chat", "say", "read", "exit"],
    "room": ["room", "join", "leave", "invite", "say", "late"],
    "feed": ["fyp", "next", "hold", "resume"],
    "moderation": ["mute", "unmute", "kick", "mod", "unmod"],
    "help": ["help"],
    "sync": ["sync"],
    "node": ["node"],
}

MODULE_DISPATCH = {
    "auth": auth.dispatch,
    "post": post.dispatch,
    "profile": profile.dispatch,
    "follow": follow.dispatch,
    "chat": chat.dispatch,
    "room": room.dispatch,
    "feed": feed.dispatch,
    "moderation": moderation.dispatch,
    "help": help.dispatch,
    "sync": SyncCommand.dispatch,
    "node": node.dispatch,
}

COMMAND_TO_MODULE = {cmd: module for module, cmds in COMMAND_MODULES.items() for cmd in cmds}

# Room-only commands
ROOM_COMMANDS = {"late", "invite"}
MOD_COMMANDS = {"mute", "unmute", "kick", "mod", "unmod"}
ROOM_ONLY = ROOM_COMMANDS.union(MOD_COMMANDS)
AUTO_SYNC_BEFORE = {
    "fyp",
    "next",
    "profile",
    "chat",
    "read",
    "room",
    "join",
    "late",
    "say",
    "invite",
    "mute",
    "unmute",
    "kick",
    "mod",
    "unmod",
}
AUTO_SYNC_AFTER = {
    "register",
    "login",
    "post",
    "comment",
    "share",
    "quote",
    "follow",
    "unfollow",
    "say",
    "invite",
    "mute",
    "unmute",
    "kick",
    "mod",
    "unmod",
}

def get_prompt():
    if state.mode == Mode.CHAT and state.current_chat:
        return f"[chat:@{state.current_chat}] > "
    elif state.mode == Mode.ROOM and state.current_room:
        return f"[forum:{state.current_room}] > "
    elif state.mode == Mode.PROFILE:
        return "[profile] > "
    else:
        return "[fyp:global] > "

def main_loop():
    print("Welcome to Beep CLI v0.2")
    if state.user:
        print(f"[AUTH] Restored session for '{state.user}'")

    while True:
        try:
            line = input(get_prompt()).strip()
            if not line:
                continue

            parts = shlex.split(line)
            if not parts or parts[0] != "beep":
                print("All commands must start with 'beep'")
                continue

            parts = parts[1:]  # remove 'beep'
            if not parts:
                print("No command provided after 'beep'")
                continue

            cmd_name = parts[0]
            args = " ".join(parts[1:]) if len(parts) > 1 else ""

            if cmd_name in AUTO_SYNC_BEFORE:
                sync(verbose=False)

            # --- SYSTEM LAYER (peer / sync / node) ---
            if cmd_name == "peer":
                if len(parts) >= 3 and parts[1] == "add":
                    peer_url = add_peer(parts[2])
                    print(f"peer added: {peer_url}")
                elif len(parts) >= 3 and parts[1] == "remove":
                    peer_url = remove_peer(parts[2])
                    print(f"peer removed: {peer_url}")
                elif len(parts) >= 2 and parts[1] == "list":
                    peers = load_peers()
                    if not peers:
                        print("No peers configured.")
                    else:
                        print("Peers:")
                        for peer in peers:
                            print(f" - {peer}")
                else:
                    print("Usage: beep peer add <url> | beep peer remove <url> | beep peer list")
                continue

            elif cmd_name == "sync":
                sync()
                print("sync complete")
                continue

            elif cmd_name == "node":
                if len(parts) >= 2 and parts[1] == "run":
                    port = 8000
                    if "--port" in parts:
                        try:
                            port_index = parts.index("--port") + 1
                            port = int(parts[port_index])
                        except:
                            print("Invalid port. Using default 8000")

                    run_node(port=port)
                else:
                    print("Usage: beep node run --port <port>")
                continue

            # --- Route 'say' based on mode ---
            if cmd_name == "say":
                if state.mode == Mode.CHAT:
                    chat.dispatch(cmd_name, args, state)
                elif state.mode == Mode.ROOM:
                    room.dispatch(cmd_name, args, state)
                else:
                    print("Error: 'say' must be used inside a chat or room")
                continue  # done with this loop iteration

            # --- Determine command module ---
            module_name = COMMAND_TO_MODULE.get(cmd_name)
            if not module_name:
                print(f"Unknown command: {cmd_name}")
                continue

            # --- Handle room-only commands ---
            if cmd_name in ROOM_ONLY:
                if state.mode != Mode.ROOM:
                    print(f"Error: '{cmd_name}' can only be used inside a room")
                    continue

                if cmd_name in ROOM_COMMANDS:
                    room.dispatch(cmd_name, args, state)
                else:  # moderation commands
                    moderation.dispatch(cmd_name, args, state)
                continue  # done with this loop iteration

            # --- Enforce commands that cannot be used inside rooms ---
            if state.mode == Mode.ROOM and cmd_name not in ROOM_ONLY and cmd_name != "leave":
                print(f"Error: '{cmd_name}' cannot be used inside a room")
                continue

            # --- Dispatch normal commands ---
            MODULE_DISPATCH[module_name](cmd_name, args, state)

            if cmd_name in AUTO_SYNC_AFTER:
                sync(verbose=False)

        except KeyboardInterrupt:
            print("\nExiting Beep CLI. Bye!")
            break
        except Exception as e:
            print(f"Error: {e}")
