# commands/chat.py
"""Chat-related CLI commands."""

import shlex
from datetime import datetime

from core.identity import build_identity_handle, find_identity_matches
from state import Mode
from storage.fs import BeepFS
from core.types import CommandState

fs = BeepFS()
DEFAULT_READ = 10


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    try:
        parts = shlex.split(args) if args else []
    except ValueError as exc:
        print(f"Error: {exc}")
        return
    user = state.user

    if not user:
        print(f"Error: You must be logged in to use '{cmd}'")
        return

    if cmd == "chat":
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
        if target == user:
            print("Error: You cannot chat with yourself")
            return

        matches = find_identity_matches(target)
        if not matches:
            print(f"Error: User '{target}' is not known locally")
            return
        if len(matches) > 1:
            print(f"Error: '{target}' is ambiguous. Use a handle:")
            for match in matches:
                print(f" - {build_identity_handle(match['username'], match['pubkey'])}")
            return

        target_user = matches[0]["username"]
        if target_user == user:
            print("Error: You cannot chat with yourself")
            return

        message_tokens = [part for part in parts[1:] if part != "--live"]
        try:
            message, cipher_profile = _extract_cipher_message(message_tokens)
        except ValueError as exc:
            print(f"Error: {exc}")
            return
        try:
            fs.create_chat(None, user, target_user)
        except ValueError as e:
            print(f"Error: {e}")
            return

        state.enter_chat(target_user)
        if message:
            try:
                fs.chat_say(target_user, user, message, cipher_profile=cipher_profile)
                suffix = f" with cipher {cipher_profile}" if cipher_profile else ""
                print(f"[CHAT] message sent{suffix}")
            except (PermissionError, FileNotFoundError, ValueError) as e:
                print(f"Error: {e}")
                return
        print(f"Entered chat with {target_user}")
        return

    if cmd == "say":
        if state.mode != Mode.CHAT:
            print("Error: 'say' can only be used inside a chat")
            return
        try:
            message, cipher_profile = _extract_cipher_message(parts)
        except ValueError as exc:
            print(f"Error: {exc}")
            return
        if not message:
            print("Error: message required")
            return
        if not state.current_chat:
            print("Error: No active chat")
            return

        try:
            fs.chat_say(
                state.current_chat,
                user,
                message,
                cipher_profile=cipher_profile,
            )
            suffix = f" with cipher {cipher_profile}" if cipher_profile else ""
            print(f"[CHAT] message sent{suffix}")
        except (PermissionError, FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
        return

    if cmd == "read":
        if state.mode != Mode.CHAT:
            print("Error: 'read' can only be used inside a chat")
            return
        if not state.current_chat:
            print("Error: No active chat")
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
        display.sort(key=lambda message: message["timestamp"])

        for message in display:
            timestamp = datetime.fromtimestamp(message["timestamp"]).strftime("%H:%M")
            print(f"[{timestamp}] {message['sender']}: {message['content']}")
        return

    if cmd == "exit":
        if state.mode != Mode.CHAT:
            print("Error: Not in a chat")
            return

        print("Left chat")
        state.exit_chat()
        return

    print(f"Unknown chat command: {cmd}")


def _extract_cipher_message(parts: list[str]) -> tuple[str, str | None]:
    """Split message tokens from an optional --cipher profile flag."""

    cipher_profile: str | None = None
    message_parts: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "--cipher":
            if index + 1 >= len(parts):
                raise ValueError("--cipher requires a profile")
            cipher_profile = parts[index + 1]
            index += 2
            continue
        message_parts.append(part)
        index += 1
    return " ".join(message_parts).strip(), cipher_profile
