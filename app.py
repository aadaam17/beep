"""Main application entry point and command dispatch for the Beep CLI."""

from __future__ import annotations

import shlex
import time
from datetime import datetime
from typing import Callable

from core.feed import get_all_posts, get_followed_posts
from core.thread_view import print_thread
from core.types import BeepObjectRecord
from state import AppState, FeedKind, Mode
from commands import (
    auth,
    backup,
    chat,
    connect,
    feed,
    follow,
    help,
    moderation,
    network,
    node,
    post,
    profile,
    restore,
    relay,
    room,
    storage as storage_cmd,
    sync,
    view,
)
from commands.sync import SyncCommand

from network.node_manager import clear_node_runtime, ensure_background_node
from network.peers import add_peer, load_peers, remove_peer
from network.sync import sync
from storage.fs import BeepFS
from storage.presence import publish_local_presence
from storage.profile import get_effective_following

state = AppState()
AppDispatcher = Callable[[str, str, AppState], None]
fs = BeepFS()

# Mapping commands to their dispatch modules
COMMAND_MODULES: dict[str, list[str]] = {
    "auth": ["register", "login", "logout"],
    "post": ["post", "comment", "share", "quote", "delete"],
    "profile": ["profile"],
    "follow": ["follow", "unfollow"],
    "chat": ["chat", "say", "read", "exit"],
    "room": ["room", "join", "leave", "invite", "say", "late", "dissolve"],
    "feed": ["fyp", "next", "hold", "resume"],
    "moderation": ["mute", "unmute", "kick", "mod", "unmod"],
    "backup": ["backup"],
    "connect": ["connect"],
    "network": ["network"],
    "restore": ["restore"],
    "relay": ["relay"],
    "help": ["help"],
    "view": ["view"],
    "sync": ["sync"],
    "node": ["node"],
    "storage": ["storage"],
}

MODULE_DISPATCH: dict[str, AppDispatcher] = {
    "auth": auth.dispatch,
    "post": post.dispatch,
    "profile": profile.dispatch,
    "follow": follow.dispatch,
    "chat": chat.dispatch,
    "room": room.dispatch,
    "feed": feed.dispatch,
    "moderation": moderation.dispatch,
    "backup": backup.dispatch,
    "connect": connect.dispatch,
    "network": network.dispatch,
    "restore": restore.dispatch,
    "relay": relay.dispatch,
    "help": help.dispatch,
    "view": view.dispatch,
    "sync": SyncCommand.dispatch,
    "node": node.dispatch,
    "storage": storage_cmd.dispatch,
}

COMMAND_TO_MODULE: dict[str, str] = {
    cmd: module for module, cmds in COMMAND_MODULES.items() for cmd in cmds
}

# Room-only commands
ROOM_COMMANDS = {"late", "invite", "dissolve"}
MOD_COMMANDS = {"mute", "unmute", "kick", "mod", "unmod"}
ROOM_ONLY = ROOM_COMMANDS.union(MOD_COMMANDS)
AUTO_SYNC_BEFORE = {
    "connect",
    "relay",
    "fyp",
    "next",
    "profile",
    "view",
    "chat",
    "read",
    "room",
    "join",
    "late",
    "say",
    "invite",
    "dissolve",
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
    "dissolve",
    "mute",
    "unmute",
    "kick",
    "mod",
    "unmod",
}

def get_prompt() -> str:
    if state.mode == Mode.CHAT and state.current_chat:
        return f"[shell:chat:@{state.current_chat}] > "
    elif state.mode == Mode.ROOM and state.current_room:
        return f"[shell:room:{state.current_room}] > "
    elif state.mode == Mode.PROFILE:
        return "[shell:profile] > "
    elif state.mode == Mode.FOLLOWED_FYP:
        return "[shell:fyp:followed] > "
    else:
        return "[shell:fyp:global] > "


def _ensure_background_node_for_session() -> None:
    """Silently ensure a local background node exists for the active session."""

    if state.user is None or state.pubkey is None:
        return
    runtime = ensure_background_node(state.user, state.pubkey)
    if runtime is not None and isinstance(runtime["url"], str):
        publish_local_presence(state.user, runtime["url"])

def initialize_session(*, announce: bool = True) -> None:
    """Refresh persisted session state before running commands."""

    if state.user:
        if announce:
            print(f"[AUTH] Restored session for '{state.user}'")
        _ensure_background_node_for_session()


def refresh_runtime_session() -> None:
    """Refresh session state between commands or live ticks."""

    session_status = state.refresh_session()
    if session_status == "changed" and state.user:
        print(f"[AUTH] Session switched to '{state.user}'.")
        _ensure_background_node_for_session()
    elif session_status == "cleared":
        print("[AUTH] Session ended. Logged out in this terminal too.")
        clear_node_runtime()


def execute_beep_parts(parts: list[str], *, announce_context: bool = False) -> bool:
    """Execute a parsed command list after the leading `beep` token."""

    if not parts:
        print("No command provided after 'beep'")
        return True

    if "--live" in parts:
        run_live_mode(parts)
        return True

    previous_mode = state.mode
    previous_chat = state.current_chat
    previous_room = state.current_room

    cmd_name = parts[0]
    args = " ".join(parts[1:]) if len(parts) > 1 else ""

    if cmd_name in AUTO_SYNC_BEFORE:
        sync(verbose=False)

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
        return True

    if cmd_name == "sync":
        SyncCommand.dispatch(cmd_name, args, state)
        return True

    if cmd_name == "node":
        node.dispatch(cmd_name, args, state)
        return True

    if cmd_name == "shell":
        launch_textual_shell()
        return True

    if cmd_name == "say":
        if state.mode == Mode.CHAT:
            chat.dispatch(cmd_name, args, state)
        elif state.mode == Mode.ROOM:
            room.dispatch(cmd_name, args, state)
        else:
            print("Error: 'say' must be used inside a chat or room")
        return True

    module_name = COMMAND_TO_MODULE.get(cmd_name)
    if not module_name:
        print(f"Unknown command: {cmd_name}")
        return False

    if cmd_name in ROOM_ONLY:
        if state.mode != Mode.ROOM:
            print(f"Error: '{cmd_name}' can only be used inside a room")
            return True

        if cmd_name in ROOM_COMMANDS:
            room.dispatch(cmd_name, args, state)
        else:
            moderation.dispatch(cmd_name, args, state)
        return True

    if state.mode == Mode.ROOM and cmd_name not in ROOM_ONLY and cmd_name != "leave":
        print(f"Error: '{cmd_name}' cannot be used inside a room")
        return True

    MODULE_DISPATCH[module_name](cmd_name, args, state)

    if cmd_name in {"register", "login"}:
        _ensure_background_node_for_session()
    elif cmd_name == "logout":
        clear_node_runtime()

    if cmd_name in AUTO_SYNC_AFTER:
        sync(verbose=False)

    if announce_context:
        _announce_shell_context_change(
            previous_mode,
            previous_chat,
            previous_room,
        )

    return True


def execute_command_line(line: str, *, announce_context: bool = False) -> bool:
    """Parse and execute a single full CLI command line."""

    parts = shlex.split(line)
    if not parts or parts[0] != "beep":
        print("All commands must start with 'beep'")
        return False

    return execute_beep_parts(parts[1:], announce_context=announce_context)


def run_shell() -> None:
    """Run the Textual interactive shell mode."""

    try:
        launch_textual_shell()
        return
    except ModuleNotFoundError as exc:
        if exc.name not in {"textual", "textual.app", "textual.widgets"}:
            raise
        print("[SHELL] Textual is not installed yet. Falling back to classic shell.")

    _run_legacy_shell()


def run_command_shell() -> None:
    """Run the original persistent text command shell."""

    _run_legacy_shell()


def launch_textual_shell() -> None:
    """Launch the Textual-powered Beep shell UI."""

    from ui.app import launch_shell_app

    initialize_session(announce=False)
    launch_shell_app()


def _run_legacy_shell() -> None:
    """Run the original line-oriented shell as a fallback."""

    _print_shell_banner()
    initialize_session()

    while True:
        try:
            refresh_runtime_session()

            line = input(get_prompt()).strip()
            if not line:
                continue
            execute_command_line(line, announce_context=True)

        except KeyboardInterrupt:
            print("\nExiting Beep CLI. Bye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def run_live_mode(parts: list[str], *, refresh_seconds: float = 5.0) -> None:
    """Run a lightweight refreshing command mode."""

    if not parts:
        print("Usage: beep <command> --live")
        return

    cmd_name = parts[0]
    live_parts = [part for part in parts if part != "--live"]

    initialize_session(announce=False)

    if cmd_name == "fyp":
        print("[LIVE] Starting live feed. Press Ctrl+C to stop.")
        _run_live_feed(live_parts, refresh_seconds=refresh_seconds)
        return

    if cmd_name == "chat":
        _run_live_chat(live_parts, refresh_seconds=refresh_seconds)
        return

    if cmd_name in {"join", "room"}:
        _run_live_room(live_parts, refresh_seconds=refresh_seconds)
        return

    if cmd_name == "network" and len(live_parts) >= 2 and live_parts[1] == "check":
        print("[LIVE] Starting live network checks. Press Ctrl+C to stop.")
        _run_live_network_check(live_parts, refresh_seconds=refresh_seconds)
        return

    print(
        "[LIVE] Currently supported: "
        "beep fyp --live | beep chat <user> --live | "
        "beep join <room> --live | beep network check --live"
    )


def run_one_shot(parts: list[str]) -> bool:
    """Run a single command-mode invocation."""

    initialize_session(announce=False)
    refresh_runtime_session()
    return execute_beep_parts(parts)


def main_loop() -> None:
    """Backward-compatible alias for the interactive shell."""

    run_shell()


def _run_live_feed(parts: list[str], *, refresh_seconds: float) -> None:
    """Continuously append newly seen feed posts instead of redrawing everything."""

    feed_type = _live_feed_type(parts)
    state.switch_fyp(feed_type)
    state.fyp_index = 0

    sync(verbose=False)
    posts = _current_live_feed_posts(feed_type)
    seen_ids = {post["id"] for post in posts}

    print(
        f"[LIVE] Starting {feed_type} feed. "
        "Showing the latest posts first. Press Ctrl+C to stop."
    )
    if not posts:
        print("[LIVE] No posts yet. Waiting for new posts...")
    else:
        print(f"[LIVE] Initial snapshot: {len(posts)} post(s)")
        print()
        for post in posts:
            print_thread(post["id"])
            print()

    while True:
        try:
            refresh_runtime_session()
            sync(verbose=False)
            posts = _current_live_feed_posts(feed_type)
            new_posts = [post for post in posts if post["id"] not in seen_ids]
            if new_posts:
                for post in reversed(new_posts):
                    seen_ids.add(post["id"])
                    print("[LIVE][NEW]")
                    print_thread(post["id"])
                    print()
            time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\n[LIVE] Stopped.")
            break


def _run_live_chat(parts: list[str], *, refresh_seconds: float) -> None:
    """Tail new direct messages for a chat target."""

    if len(parts) < 2:
        print("[LIVE] Usage: beep chat <username|handle> --live")
        return

    refresh_runtime_session()
    if not execute_beep_parts(parts):
        return
    if state.user is None or state.current_chat is None:
        print("[LIVE] Could not enter chat.")
        return

    user = state.user
    peer = state.current_chat
    _, seen = fs.chat_read_messages(peer, user, start=0, limit=100000)
    print(f"[LIVE] Tailing chat with {peer}. Press Ctrl+C to stop.")

    while True:
        try:
            refresh_runtime_session()
            messages, total = fs.chat_read_messages(
                peer,
                user,
                start=seen,
                limit=100000,
            )
            for message in messages:
                _print_live_message(message["timestamp"], message["sender"], message["content"])
            seen = total
            time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\n[LIVE] Stopped.")
            break


def _run_live_room(parts: list[str], *, refresh_seconds: float) -> None:
    """Tail new room messages for a joined room."""

    if len(parts) < 2:
        print("[LIVE] Usage: beep join <room> --live")
        return

    refresh_runtime_session()
    if not execute_beep_parts(parts):
        return
    if state.user is None or state.current_room is None:
        print("[LIVE] Could not enter room.")
        return

    user = state.user
    room_name = state.current_room
    _, seen = fs.read_messages(room_name, user, start=0, limit=100000)
    print(f"[LIVE] Tailing room {room_name}. Press Ctrl+C to stop.")

    while True:
        try:
            refresh_runtime_session()
            messages, total = fs.read_messages(
                room_name,
                user,
                start=seen,
                limit=100000,
            )
            for message in messages:
                _print_live_message(message["timestamp"], message["sender"], message["content"])
            seen = total
            time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\n[LIVE] Stopped.")
            break


def _run_live_network_check(parts: list[str], *, refresh_seconds: float) -> None:
    """Continuously rerun network checks."""

    while True:
        try:
            refresh_runtime_session()
            execute_beep_parts(parts)
            time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\n[LIVE] Stopped.")
            break


def _print_live_message(timestamp: float, sender: str, content: str) -> None:
    """Render a single tailed chat or room message."""

    clock = datetime.fromtimestamp(timestamp).strftime("%H:%M")
    print(f"[{clock}] {sender}: {content}")


def _live_feed_type(parts: list[str]) -> FeedKind:
    """Parse the requested live feed type from command parts."""

    requested = "global"
    for part in parts[1:]:
        if part == "--live":
            continue
        requested = part
        break

    if requested not in {"global", "followed"}:
        print("[LIVE] Usage: beep fyp [global|followed] --live")
        return "global"

    return requested


def _current_live_feed_posts(feed_type: FeedKind) -> list[BeepObjectRecord]:
    """Load the current live feed using the canonical feed backends."""

    if feed_type == "followed":
        if not state.user:
            print("[LIVE] Login required for followed feed. Showing global feed.")
            return get_all_posts()
        following = get_effective_following(state.pubkey or "")
        return get_followed_posts(following)
    return get_all_posts()


def _print_shell_banner() -> None:
    """Render a clearer shell-mode welcome banner."""

    print("Beep Shell")
    print("==========")
    print("Command mode: `beep post \"hello\"`")
    print("Live mode: `beep fyp --live`")
    print("Interactive mode: this shell")
    print("Type `beep help` for commands. Press Ctrl+C to exit.")


def _announce_shell_context_change(
    previous_mode: Mode,
    previous_chat: str | None,
    previous_room: str | None,
) -> None:
    """Print a shell-only banner when context changes."""

    if (
        previous_mode == state.mode
        and previous_chat == state.current_chat
        and previous_room == state.current_room
    ):
        return

    if state.mode == Mode.CHAT and state.current_chat:
        print(f"[SHELL] Context -> chat @{state.current_chat}")
        return

    if state.mode == Mode.ROOM and state.current_room:
        print(f"[SHELL] Context -> room {state.current_room}")
        return

    if state.mode == Mode.PROFILE:
        print("[SHELL] Context -> profile")
        return

    if state.mode == Mode.FOLLOWED_FYP:
        print("[SHELL] Context -> feed followed")
        return

    print("[SHELL] Context -> feed global")
