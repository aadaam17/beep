# commands/relay.py
"""Relay endpoint configuration commands."""

from __future__ import annotations

from core.types import CommandState
from network.peers import normalize_peer_url
from network.reachability import probe_endpoint_health
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
        print(f" - node mode: {'on' if policy['node_autostart'] else 'off'}")
        print(f" - presence ttl: {policy['presence_ttl_seconds']}s")
        print(f" - presence refresh: {policy['presence_refresh_seconds']}s")
        print(f" - max object bytes: {policy['max_object_bytes']}")
        print(f" - max posts/min/ip: {policy['max_posts_per_minute']}")
        print(f" - max objects/author: {policy['max_objects_per_author']}")
        print(f" - max objects/ip: {policy['max_objects_per_ip']}")
        print(f" - retention limit: {policy['relay_retention_limit']}")
        print(f" - relay-only mode: {'on' if policy['relay_only_mode'] else 'off'}")
        print(f" - peer auth: {'on' if policy['peer_auth_required'] else 'off'}")
        print(f" - denylisted authors: {len(policy['denylisted_authors'])}")
        print(f" - denylisted ips: {len(policy['denylisted_ips'])}")
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
            "beep relay policy set public-endpoint <url|clear> | "
            "beep relay policy set max-object-bytes <bytes> | "
            "beep relay policy set max-posts-per-minute <n> | "
            "beep relay policy set max-objects-per-author <n> | "
            "beep relay policy set max-objects-per-ip <n> | "
            "beep relay policy set retention-limit <n> | "
            "beep relay policy set relay-only <on|off> | "
            "beep relay policy set peer-auth <on|off> | "
            "beep relay policy set peer-token <token|clear> | "
            "beep relay policy set deny-author <pubkey> | "
            "beep relay policy set allow-author <pubkey> | "
            "beep relay policy set deny-ip <ip> | "
            "beep relay policy set allow-ip <ip>"
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
        print(f"[RELAY] node mode: {'on' if policy['node_autostart'] else 'off'}")
        return

    if key in {"relay-only", "peer-auth"} and value in {"on", "off"}:
        field = "relay_only_mode" if key == "relay-only" else "peer_auth_required"
        policy = update_network_policy(**{field: value == "on"})
        print(f"[RELAY] {key}: {'on' if policy[field] else 'off'}")
        return

    if key == "peer-token":
        policy = update_network_policy(peer_auth_token="" if value == "clear" else value)
        print("[RELAY] peer token " + ("cleared" if value == "clear" else "updated"))
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

    numeric_fields = {
        "max-object-bytes": "max_object_bytes",
        "max-posts-per-minute": "max_posts_per_minute",
        "max-objects-per-author": "max_objects_per_author",
        "max-objects-per-ip": "max_objects_per_ip",
        "retention-limit": "relay_retention_limit",
    }
    if key in numeric_fields:
        try:
            number = int(value)
        except ValueError:
            print("[RELAY] value must be a positive integer")
            return
        if number <= 0:
            print("[RELAY] value must be a positive integer")
            return
        field = numeric_fields[key]
        policy = update_network_policy(**{field: number})
        print(f"[RELAY] {key}: {policy[field]}")
        return

    denylist_fields = {
        "deny-author": ("denylisted_authors", True),
        "allow-author": ("denylisted_authors", False),
        "deny-ip": ("denylisted_ips", True),
        "allow-ip": ("denylisted_ips", False),
    }
    if key in denylist_fields:
        field, add = denylist_fields[key]
        policy = load_network_policy()
        values = list(policy[field])
        if add and value not in values:
            values.append(value)
        if not add:
            values = [item for item in values if item != value]
        policy = update_network_policy(**{field: values})
        print(f"[RELAY] {field}: {len(policy[field])}")
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
        health = probe_endpoint_health(endpoint)
        if health["status"] == "reachable":
            print("[RELAY] public endpoint is reachable")
        else:
            print(
                "[RELAY] warning: public endpoint is not reachable yet"
                + (f" ({health['error']})" if health["error"] else "")
            )
        return

    print("[RELAY] invalid policy setting")
