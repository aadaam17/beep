# commands/network.py
"""Unified network bootstrap, status, and health commands."""

from __future__ import annotations

from core.types import CommandState
from network.node_manager import load_node_runtime
from network.peers import add_peer, load_peers, normalize_peer_url
from network.reachability import probe_endpoint
from storage.network_policy import load_network_policy, order_network_targets
from storage.relay import add_relay, load_relays


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle user-facing network commands."""

    if cmd != "network":
        return

    parts = args.split()
    if not parts or parts[0] == "status":
        _status()
        return
    if parts[0] == "setup":
        _setup(parts[1:])
        return
    if parts[0] == "check":
        _check()
        return

    print("Usage: beep network [status|setup|check]")


def _status() -> None:
    """Render a high-level network summary."""

    policy = load_network_policy()
    peers = load_peers()
    relays = load_relays()
    targets = order_network_targets(peers, relays)
    runtime = load_node_runtime()

    print("[NETWORK] Status")
    print(
        f" - strategy: {policy['strategy']} | "
        f"relay {'on' if policy['relay_enabled'] else 'off'} | "
        f"node mode {'on' if policy['node_autostart'] else 'off'}"
    )
    print(
        f" - peers: {len(peers)} | relays: {len(relays)} | "
        f"discovery targets: {len(targets)}"
    )
    print(
        f" - public endpoint: {policy['public_endpoint'] or '(not set)'}"
    )
    print(
        f" - presence ttl: {policy['presence_ttl_seconds']}s | "
        f"refresh: {policy['presence_refresh_seconds']}s"
    )
    if runtime is None:
        print(" - local node: not running")
    else:
        print(f" - local node: {runtime['url']} (pid {runtime['pid']})")

    if not targets:
        print("[NETWORK] No peers or relays configured yet.")
        print("[NETWORK] Use: beep network setup")


def _setup(parts: list[str]) -> None:
    """Guide or apply basic bootstrap network setup."""

    if not parts:
        _print_setup_guidance()
        return

    if len(parts) >= 2 and parts[0] == "--relay":
        relay_url = add_relay(parts[1])
        print(f"[NETWORK] Added relay {relay_url}")
        print("[NETWORK] Run `beep network check` to verify reachability.")
        return

    if len(parts) >= 2 and parts[0] == "--peer":
        peer_url = add_peer(parts[1])
        print(f"[NETWORK] Added peer {peer_url}")
        print("[NETWORK] Run `beep network check` to verify reachability.")
        return

    print("Usage: beep network setup [--relay <url> | --peer <url>]")


def _check() -> None:
    """Probe configured discovery targets and report reachability."""

    peers = load_peers()
    relays = load_relays()
    targets = order_network_targets(peers, relays)
    if not targets:
        print("[NETWORK] No peers or relays configured to check.")
        print("[NETWORK] Use: beep network setup")
        return

    print("[NETWORK] Reachability check")
    reachable = 0
    for target in targets:
        kind = "relay" if target in relays else "peer"
        status = probe_endpoint(target)
        if status == "reachable":
            reachable += 1
            print(f" - {target} [{kind}] reachable")
        else:
            print(f" - {target} [{kind}] unreachable")

    print(f"[NETWORK] Reachable targets: {reachable}/{len(targets)}")
    if reachable == 0:
        print("[NETWORK] Nothing is reachable right now.")
        print("[NETWORK] Check that the URL is public, the node is running, and the policy allows this route.")


def _print_setup_guidance() -> None:
    """Explain the next bootstrap step based on current network state."""

    peers = load_peers()
    relays = load_relays()
    policy = load_network_policy()

    print("[NETWORK] Setup")
    if peers or relays:
        print("[NETWORK] You already have discovery targets configured.")
        print("[NETWORK] Use `beep network status` or `beep network check` next.")
        return

    print("[NETWORK] This node is not connected to anyone yet.")
    print("[NETWORK] Choose one of these:")
    print(" - Direct peer: beep network setup --peer <url>")
    print(" - Relay-assisted: beep network setup --relay <url>")
    if not policy["relay_enabled"]:
        print("[NETWORK] Relay use is currently disabled by policy.")
        print("[NETWORK] Enable it with: beep relay policy set enabled on")
