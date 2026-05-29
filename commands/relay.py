# commands/relay.py
"""Relay endpoint configuration commands."""

from __future__ import annotations

from core.types import CommandState
from network.peers import normalize_peer_url
from storage.network_policy import load_network_policy, update_network_policy
from storage.relay import add_relay, load_relays, remove_relay


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle relay configuration commands."""

    if cmd != "relay":
        return

    parts = args.split()
    if parts and parts[0] == "policy":
        _dispatch_policy(parts[1:])
        return
    if len(parts) >= 2 and parts[0] == "add":
        relay = add_relay(parts[1])
        print(f"relay added: {relay}")
        return
    if len(parts) >= 2 and parts[0] == "remove":
        relay = remove_relay(parts[1])
        print(f"relay removed: {relay}")
        return
    if parts and parts[0] == "list":
        relays = load_relays()
        if not relays:
            print("No relays configured.")
            return
        print("Relays:")
        for relay in relays:
            print(f" - {relay}")
        return

    print(
        "Usage: beep relay add <url> | beep relay remove <url> | "
        "beep relay list | beep relay policy [set ...]"
    )


def _dispatch_policy(parts: list[str]) -> None:
    """Handle relay policy inspection and updates."""

    if not parts:
        policy = load_network_policy()
        print("[RELAY] Network policy")
        print(f" - relay enabled: {'on' if policy['relay_enabled'] else 'off'}")
        print(f" - strategy: {policy['strategy']}")
        print(f" - node autostart: {'on' if policy['node_autostart'] else 'off'}")
        print(f" - presence ttl: {policy['presence_ttl_seconds']}s")
        print(f" - presence refresh: {policy['presence_refresh_seconds']}s")
        print(
            f" - public endpoint: {policy['public_endpoint'] or '(not set)'}"
        )
        return

    if len(parts) < 3 or parts[0] != "set":
        print(
            "Usage: beep relay policy | "
            "beep relay policy set enabled <on|off> | "
            "beep relay policy set strategy <prefer-direct|direct-only|relay-first> | "
            "beep relay policy set autostart <on|off> | "
            "beep relay policy set presence-ttl <seconds> | "
            "beep relay policy set presence-refresh <seconds> | "
            "beep relay policy set public-endpoint <url|clear>"
        )
        return

    key = parts[1]
    value = parts[2]

    if key == "enabled" and value in {"on", "off"}:
        policy = update_network_policy(relay_enabled=value == "on")
        print(f"[RELAY] relay enabled: {'on' if policy['relay_enabled'] else 'off'}")
        return

    if key == "strategy" and value in {"prefer-direct", "direct-only", "relay-first"}:
        policy = update_network_policy(strategy=value)
        print(f"[RELAY] strategy set to {policy['strategy']}")
        return

    if key == "autostart" and value in {"on", "off"}:
        policy = update_network_policy(node_autostart=value == "on")
        print(f"[RELAY] node autostart: {'on' if policy['node_autostart'] else 'off'}")
        return

    if key in {"presence-ttl", "presence-refresh"}:
        try:
            seconds = int(value)
        except ValueError:
            print("[RELAY] value must be a positive integer number of seconds")
            return
        if seconds <= 0:
            print("[RELAY] value must be a positive integer number of seconds")
            return
        if key == "presence-ttl":
            policy = update_network_policy(presence_ttl_seconds=seconds)
            print(f"[RELAY] presence ttl: {policy['presence_ttl_seconds']}s")
            return
        policy = update_network_policy(presence_refresh_seconds=seconds)
        print(f"[RELAY] presence refresh: {policy['presence_refresh_seconds']}s")
        return

    if key == "public-endpoint":
        if value == "clear":
            policy = update_network_policy(public_endpoint="")
            print("[RELAY] public endpoint cleared")
            return
        try:
            endpoint = normalize_peer_url(value)
        except ValueError:
            print("[RELAY] public endpoint must be a valid URL")
            return
        policy = update_network_policy(public_endpoint=endpoint)
        print(f"[RELAY] public endpoint: {policy['public_endpoint']}")
        return

    print("[RELAY] invalid policy setting")
