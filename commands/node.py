"""Node management commands."""

from __future__ import annotations

import subprocess
import sys

from core.types import CommandState
from network.node_capability import detect_node_capability
from network.node_manager import (
    ensure_background_node,
    load_node_runtime,
    node_log_path,
    node_log_tail,
    node_runtime_reachable,
    stop_background_node,
)
from storage.network_policy import load_network_policy, update_network_policy
from storage.presence import publish_local_presence

_PROMPTED_THIS_PROCESS = False


def run_node(**kwargs: object) -> None:
    """Lazy wrapper around the optional FastAPI node runtime."""

    from network.node import run_node as _run_node

    _run_node(**kwargs)


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    if cmd != "node":
        return

    parts = args.split()
    action = parts[0] if parts else "status"

    if action == "status":
        _status()
        return

    if action == "enable":
        _enable(state)
        return

    if action == "disable":
        _disable()
        return

    if action != "run":
        print("Usage: node status | node enable | node disable | node run --port <port>")
        return

    if state.user is None or state.pubkey is None:
        print("You must be logged in to run a node.")
        return

    if not _ensure_server_dependencies():
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


def _status() -> None:
    """Print node-mode policy and runtime status."""

    policy = load_network_policy()
    capability = detect_node_capability()
    runtime = load_node_runtime()

    print("[NODE] Status")
    print(f" - node mode: {'enabled' if policy['node_autostart'] else 'disabled'}")
    device_status = (
        "recommended for node mode"
        if capability.recommended
        else "client mode recommended"
    )
    print(f" - device: {device_status}")
    if capability.reasons:
        for reason in capability.reasons:
            print(f"   - {reason}")
        if capability.can_override:
            print("   - override available with: beep node enable")
    print(
        " - server dependencies: "
        + ("installed" if capability.server_dependencies_installed else "missing")
    )
    if runtime is None:
        print(" - local node: not running")
        tail = node_log_tail(max_lines=3)
        if tail:
            print(f" - last log: {tail[-1]}")
    else:
        health = "reachable" if node_runtime_reachable(runtime) else "unreachable"
        print(f" - local node: {runtime['url']} (pid {runtime['pid']}, {health})")
    print(f" - log file: {node_log_path()}")


def _enable(state: CommandState) -> None:
    """Enable node mode and start a background node when possible."""

    capability = detect_node_capability()

    if capability.recommended:
        print("Node mode is supported on this device.")
    else:
        print("Node mode override requested.")
        print("This device is not recommended for hosting:")
        for reason in capability.reasons:
            print(f" - {reason}")

    if not _ensure_server_dependencies():
        update_network_policy(node_prompted=True)
        print("Node mode was not enabled.")
        return

    update_network_policy(node_autostart=True, node_prompted=True)

    if state.user is None or state.pubkey is None:
        print("Node mode is enabled. Log in to start hosting.")
        return

    runtime = ensure_background_node(state.user, state.pubkey)
    if runtime is None:
        print("[NODE] Could not start background node.")
        print(f"[NODE] Log file: {node_log_path()}")
        tail = node_log_tail()
        if tail:
            print("[NODE] Last node log lines:")
            for line in tail:
                print(f"  {line}")
        else:
            print(
                "[NODE] No node log was written. "
                "Try: beep node run --port 8000"
            )
        return

    publish_local_presence(state.user, runtime["url"])
    print(f"[NODE] Node mode enabled at {runtime['url']}")


def _disable() -> None:
    """Disable node mode and stop the tracked background node."""

    update_network_policy(node_autostart=False, node_prompted=True)
    stopped = stop_background_node()
    print("[NODE] Node mode disabled.")
    if stopped:
        print("[NODE] Stopped background node.")


def maybe_prompt_node_mode(state: CommandState) -> None:
    """Offer node mode once when the active device is recommended for hosting."""

    global _PROMPTED_THIS_PROCESS

    policy = load_network_policy()
    if policy["node_autostart"] or policy["node_prompted"] or _PROMPTED_THIS_PROCESS:
        return
    if not sys.stdin.isatty():
        return

    capability = detect_node_capability()
    if not capability.recommended:
        return

    _PROMPTED_THIS_PROCESS = True
    print()
    print("Beep detected that this device can participate as a network node.")
    print()
    print("Benefits:")
    print("- Helps relay content")
    print("- Improves network resilience")
    print("- Stores and synchronizes public network data")
    print()
    print("Would you like to enable node mode?")
    print()
    print("[Y] Yes")
    print("[N] No")
    print("[R] Remind me later")
    print()

    choice = input("> ").strip().lower()
    if choice in {"y", "yes"}:
        _enable(state)
        return
    if choice in {"n", "no"}:
        update_network_policy(node_prompted=True)
        print(
            "[NODE] Client mode selected. "
            "You can enable hosting later with `beep node enable`."
        )
        return

    print(
        "[NODE] Staying in client mode for now. "
        "Use `beep node enable` whenever you are ready."
    )


def _ensure_server_dependencies() -> bool:
    """Prompt to install optional server dependencies when missing."""

    capability = detect_node_capability()
    if capability.server_dependencies_installed:
        return True

    print("Server dependencies are missing.")
    if not sys.stdin.isatty():
        print('Install them with: pip install "beep-cli[server]"')
        return False

    answer = input("Install now? [Y/n] ").strip().lower()
    if answer in {"", "y", "yes"}:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "beep-cli[server]"],
            check=False,
        )
        if result.returncode == 0:
            return detect_node_capability().server_dependencies_installed
        print("[NODE] Install failed.")
        return False

    print('Install later with: pip install "beep-cli[server]"')
    return False
