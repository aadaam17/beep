# commands/moderation.py

from storage.fs import BeepFS
from state import Mode
from state import AppState

fs = BeepFS()


def dispatch(cmd: str, args: str, state: AppState) -> None:
    if state.mode != Mode.ROOM:
        print("Error: moderation commands only work in rooms")
        return

    if not state.user or not state.current_room:
        print("Error: invalid session state")
        return

    actor: str = state.user
    room_name: str = state.current_room

    target: str = args.replace("--perma", "").strip()

    if not target:
        print(f"Error: username required for '{cmd}'")
        return

    try:
        if cmd == "mod":
            result = fs.room_mod(room_name, actor, target, promote=True)
            if result == "already_mod":
                print(f"{target} is already a moderator")
            else:
                print(f"{target} is now a moderator")

        elif cmd == "unmod":
            result = fs.room_mod(room_name, actor, target, promote=False)
            if result == "not_mod":
                print(f"{target} is not a moderator")
            else:
                print(f"{target} removed from moderators")

        elif cmd == "mute":
            result = fs.room_mute(
                room_name,
                actor,
                target,
                permanent="--perma" in args,
            )
            if result == "already_muted":
                print(f"{target} is already muted")
            else:
                print(f"{target} muted")

        elif cmd == "unmute":
            result = fs.room_unmute(room_name, actor, target)
            if result == "not_muted":
                print(f"{target} is not muted")
            else:
                print(f"{target} unmuted")

        elif cmd == "kick":
            result = fs.room_kick(room_name, actor, target)
            if result == "already_banned":
                print(f"{target} is already banned")
            elif result == "not_member":
                print(f"{target} is not in the room")
            else:
                print(f"{target} kicked and banned")

        else:
            print("Unknown moderation command")

    except PermissionError as e:
        print(f"Error: {e}")
    except ValueError as e:
        print(f"Error: {e}")