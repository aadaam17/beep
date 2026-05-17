# commands/node.py

from network.node import run_node
from core.types import CommandState


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    if cmd != "node":
        return

    parts = args.split()

    if not parts or parts[0] != "run":
        print("Usage: node run --port <port>")
        return

    if state.user is None or state.pubkey is None:
        print("You must be logged in to run a node.")
        return

    port = 8000

    if "--port" in parts:
        try:
            port = int(parts[parts.index("--port") + 1])
        except (ValueError, IndexError):
            print("Invalid port. Using default 8000")

    run_node(
        port=port,
        session_username=state.user,
        session_pubkey=state.pubkey,
    )