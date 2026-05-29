# commands/room.py
"""Room management commands for creating, joining, leaving, and messaging in rooms."""

from datetime import datetime
from core.types import CommandState
from state import Mode
from storage.fs import BeepFS
from storage.profile import get_user

fs = BeepFS()
DEFAULT_LATEST = 5
EPHEMERAL_TTL_SECONDS = 86400


def _parse_ephemeral_ttl(parts: list[str]) -> int | None:
    if "--ephemeral" not in parts:
        return None

    index = parts.index("--ephemeral")

    if index + 1 >= len(parts) or parts[index + 1].startswith("--"):
        return EPHEMERAL_TTL_SECONDS

    token = parts[index + 1].strip().lower()
    if not token:
        return EPHEMERAL_TTL_SECONDS

    unit = token[-1]
    if unit.isdigit():
        value = int(token)
        multiplier = 1
    else:
        value_part = token[:-1]
        if not value_part.isdigit():
            raise ValueError(
                "Invalid ephemeral duration. Use values like 15s, 1m, 3h, or 2d."
            )
        value = int(value_part)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        multiplier = multipliers.get(unit)
        if not multiplier:
            raise ValueError(
                "Invalid ephemeral duration unit. Use s, m, h, or d."
            )

    if value <= 0:
        raise ValueError("Ephemeral duration must be greater than zero.")

    return value * multiplier


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    room_only = {"say", "late", "invite", "dissolve"}
    login_required = {"room", "join", "say", "invite", "dissolve"}

    parts = args.split() if args else []
    user_name = state.user

    if cmd in room_only and state.mode != Mode.ROOM:
        print(f"Error: '{cmd}' can only be used inside a room")
        return

    if cmd in login_required and user_name is None:
        print(f"Error: You must be logged in to use '{cmd}'")
        return

    if cmd == "room":
        if state.mode == Mode.ROOM:
            print("Error: Cannot create a new room while inside another room")
            return

        if not parts:
            rooms = fs.list_rooms()
            if not rooms:
                print("No rooms available.")
            else:
                print("Available rooms:")
                for room_name in rooms:
                    print(f" - {room_name}")
            return

        name = parts[0]
        private = "--private" in parts
        try:
            ttl = _parse_ephemeral_ttl(parts)
        except ValueError as e:
            print(f"Error: {e}")
            return
        ephemeral = ttl is not None

        try:
            if user_name is None:
                print(f"Error: You must be logged in to use '{cmd}'")
                return
            fs.create_room(name, user_name, private, ttl)
            state.enter_room(name)
            if ephemeral:
                print(f"Room created and joined: {name} (expires in {ttl}s)")
            else:
                print(f"Room created and joined: {name}")
        except ValueError as e:
            print(f"Error: {e}")
        return

    if cmd == "join":
        if state.mode == Mode.ROOM:
            print("Error: Already inside a room")
            return
        if not parts:
            print("Error: room name required")
            return

        room_name = parts[0]
        try:
            if user_name is None:
                print(f"Error: You must be logged in to use '{cmd}'")
                return
            result = fs.join_room(room_name, user_name)
            state.enter_room(room_name)
            if result != "already_member":
                print(f"Joined {room_name}")
        except PermissionError as e:
            print(f"Error: {e}")
        except ValueError as e:
            print(f"Error: {e}")
        return

    if cmd == "leave":
        if state.mode != Mode.ROOM:
            print("Error: Not in a room")
            return
        room_name = state.current_room
        if room_name is None or user_name is None:
            print("Error: No active room")
            return
        try:
            result = fs.leave_room(room_name, user_name)
            print(f"Leaving room: {room_name}")
        except ValueError as e:
            print(f"Error: {e}")
            return
        state.exit_room()
        return

    if cmd == "say":
        if not args:
            print("Error: message required")
            return
        room_name = state.current_room
        if room_name is None or user_name is None:
            print("Error: No active room")
            return
        try:
            fs.say(room_name, user_name, args)
            print("[ROOM] sent")
        except PermissionError as e:
            print(f"Error: {e}")
        return

    if cmd == "late":
        show_all = False
        num = DEFAULT_LATEST
        if parts:
            if parts[0] == "--all":
                show_all = True
            elif parts[0].isdigit():
                num = int(parts[0])

        room_name = state.current_room
        if room_name is None or user_name is None:
            print("Error: No active room")
            return

        msgs, _ = fs.read_messages(room_name, user_name)
        if not msgs:
            print("No messages in this room yet.")
            return

        display = msgs if show_all else msgs[-num:]
        display.sort(key=lambda message: message["timestamp"])

        for message in display:
            timestamp = datetime.fromtimestamp(message["timestamp"]).strftime("%H:%M")
            print(f"[{timestamp}] {message['sender']}: {message['content']}")
        return

    if cmd == "invite":
        if not parts:
            print("Error: username required to invite")
            return

        target_user = parts[0]
        if not get_user(target_user):
            print(f"Error: User '{target_user}' does not exist")
            return

        room_name = state.current_room
        if room_name is None or user_name is None:
            print("Error: No active room")
            return

        try:
            result = fs.invite(room_name, target_user, actor=user_name)
            if result == "already_member":
                print(f"{target_user} is already in the room")
            elif result == "already_invited":
                print(f"{target_user} already has a valid invite")
            else:
                print(f"Invited {target_user}")
        except ValueError as e:
            print(f"Error: {e}")
        except PermissionError as e:
            print(f"Error: {e}")
        return

    if cmd == "dissolve":
        room_name = state.current_room
        if room_name is None or user_name is None:
            print("Error: No active room")
            return
        try:
            fs.dissolve_room(room_name, user_name)
            print(f"Dissolved room {room_name}")
            state.exit_room()
        except ValueError as e:
            print(f"Error: {e}")
        except PermissionError as e:
            print(f"Error: {e}")
        return

    print(f"Unknown room command: {cmd}")
