# storage/network_policy.py
"""Persistent network policy for relay and node behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict, cast

from storage.atomic import atomic_write_json, read_json_with_backup

NetworkStrategy = Literal["prefer-direct", "direct-only", "relay-first"]


class NetworkPolicy(TypedDict):
    """Runtime network policy settings."""

    relay_enabled: bool
    node_autostart: bool
    node_prompted: bool
    strategy: NetworkStrategy
    presence_ttl_seconds: int
    presence_refresh_seconds: int
    public_endpoint: str
    max_object_bytes: int
    max_posts_per_minute: int
    max_objects_per_author: int
    max_objects_per_ip: int
    relay_retention_limit: int
    relay_only_mode: bool
    denylisted_authors: list[str]
    denylisted_ips: list[str]
    peer_auth_required: bool
    peer_auth_token: str


POLICY_FILE = Path.home() / ".beep" / "network_policy.json"
DEFAULT_POLICY: NetworkPolicy = {
    "relay_enabled": True,
    "node_autostart": False,
    "node_prompted": False,
    "strategy": "prefer-direct",
    "presence_ttl_seconds": 24 * 60 * 60,
    "presence_refresh_seconds": 15 * 60,
    "public_endpoint": "",
    "max_object_bytes": 256 * 1024,
    "max_posts_per_minute": 60,
    "max_objects_per_author": 10_000,
    "max_objects_per_ip": 20_000,
    "relay_retention_limit": 50_000,
    "relay_only_mode": False,
    "denylisted_authors": [],
    "denylisted_ips": [],
    "peer_auth_required": False,
    "peer_auth_token": "",
}


def load_network_policy() -> NetworkPolicy:
    """Load the saved network policy or return sane defaults."""

    raw = read_json_with_backup(POLICY_FILE)
    if raw is None:
        return dict(DEFAULT_POLICY)

    if not isinstance(raw, dict):
        return dict(DEFAULT_POLICY)

    data = cast(dict[str, object], raw)
    policy: NetworkPolicy = dict(DEFAULT_POLICY)

    relay_enabled = data.get("relay_enabled")
    if isinstance(relay_enabled, bool):
        policy["relay_enabled"] = relay_enabled

    node_autostart = data.get("node_autostart")
    if isinstance(node_autostart, bool):
        policy["node_autostart"] = node_autostart

    node_prompted = data.get("node_prompted")
    if isinstance(node_prompted, bool):
        policy["node_prompted"] = node_prompted

    strategy = data.get("strategy")
    if strategy in {"prefer-direct", "direct-only", "relay-first"}:
        policy["strategy"] = strategy

    presence_ttl_seconds = data.get("presence_ttl_seconds")
    if isinstance(presence_ttl_seconds, int) and presence_ttl_seconds > 0:
        policy["presence_ttl_seconds"] = presence_ttl_seconds

    presence_refresh_seconds = data.get("presence_refresh_seconds")
    if isinstance(presence_refresh_seconds, int) and presence_refresh_seconds > 0:
        policy["presence_refresh_seconds"] = presence_refresh_seconds

    public_endpoint = data.get("public_endpoint")
    if isinstance(public_endpoint, str):
        policy["public_endpoint"] = public_endpoint

    for key in (
        "max_object_bytes",
        "max_posts_per_minute",
        "max_objects_per_author",
        "max_objects_per_ip",
        "relay_retention_limit",
    ):
        value = data.get(key)
        if isinstance(value, int) and value > 0:
            policy[key] = value

    for key in ("relay_only_mode", "peer_auth_required"):
        value = data.get(key)
        if isinstance(value, bool):
            policy[key] = value

    for key in ("denylisted_authors", "denylisted_ips"):
        value = data.get(key)
        if isinstance(value, list):
            policy[key] = [item for item in value if isinstance(item, str)]

    peer_auth_token = data.get("peer_auth_token")
    if isinstance(peer_auth_token, str):
        policy["peer_auth_token"] = peer_auth_token

    return policy


def save_network_policy(policy: NetworkPolicy) -> None:
    """Persist a full network policy."""

    atomic_write_json(POLICY_FILE, policy, indent=2)


def update_network_policy(**changes: object) -> NetworkPolicy:
    """Apply validated updates to the saved network policy."""

    policy = load_network_policy()

    relay_enabled = changes.get("relay_enabled")
    if isinstance(relay_enabled, bool):
        policy["relay_enabled"] = relay_enabled

    node_autostart = changes.get("node_autostart")
    if isinstance(node_autostart, bool):
        policy["node_autostart"] = node_autostart

    node_prompted = changes.get("node_prompted")
    if isinstance(node_prompted, bool):
        policy["node_prompted"] = node_prompted

    strategy = changes.get("strategy")
    if strategy in {"prefer-direct", "direct-only", "relay-first"}:
        policy["strategy"] = strategy

    presence_ttl_seconds = changes.get("presence_ttl_seconds")
    if isinstance(presence_ttl_seconds, int) and presence_ttl_seconds > 0:
        policy["presence_ttl_seconds"] = presence_ttl_seconds

    presence_refresh_seconds = changes.get("presence_refresh_seconds")
    if isinstance(presence_refresh_seconds, int) and presence_refresh_seconds > 0:
        policy["presence_refresh_seconds"] = presence_refresh_seconds

    public_endpoint = changes.get("public_endpoint")
    if isinstance(public_endpoint, str):
        policy["public_endpoint"] = public_endpoint

    for key in (
        "max_object_bytes",
        "max_posts_per_minute",
        "max_objects_per_author",
        "max_objects_per_ip",
        "relay_retention_limit",
    ):
        value = changes.get(key)
        if isinstance(value, int) and value > 0:
            policy[key] = value

    for key in ("relay_only_mode", "peer_auth_required"):
        value = changes.get(key)
        if isinstance(value, bool):
            policy[key] = value

    for key in ("denylisted_authors", "denylisted_ips"):
        value = changes.get(key)
        if isinstance(value, list):
            policy[key] = [item for item in value if isinstance(item, str)]

    peer_auth_token = changes.get("peer_auth_token")
    if isinstance(peer_auth_token, str):
        policy["peer_auth_token"] = peer_auth_token

    save_network_policy(policy)
    return policy


def relay_enabled() -> bool:
    """Return whether relay usage is enabled."""

    return load_network_policy()["relay_enabled"]


def node_autostart_enabled() -> bool:
    """Return whether session login should auto-start a local node."""

    return load_network_policy()["node_autostart"]


def presence_ttl_seconds() -> int:
    """Return the configured presence TTL."""

    return load_network_policy()["presence_ttl_seconds"]


def presence_refresh_seconds() -> int:
    """Return the configured presence refresh interval."""

    return load_network_policy()["presence_refresh_seconds"]


def public_endpoint() -> str | None:
    """Return the configured public presence endpoint, if any."""

    endpoint = load_network_policy()["public_endpoint"].strip()
    return endpoint or None


def peer_auth_header() -> dict[str, str]:
    """Return the configured peer auth header, if enabled."""

    policy = load_network_policy()
    token = policy["peer_auth_token"].strip()
    if not policy["peer_auth_required"] or not token:
        return {}
    return {"X-Beep-Peer-Token": token}


def order_network_targets(peers: list[str], relays: list[str]) -> list[str]:
    """Return deduplicated network targets in policy order."""

    policy = load_network_policy()
    peer_list = list(peers)
    relay_list = list(relays) if policy["relay_enabled"] else []

    if policy["strategy"] == "direct-only":
        relay_list = []

    ordered_sources = (
        [relay_list, peer_list]
        if policy["strategy"] == "relay-first"
        else [peer_list, relay_list]
    )

    targets: list[str] = []
    seen: set[str] = set()
    for source in ordered_sources:
        for target in source:
            if target in seen:
                continue
            seen.add(target)
            targets.append(target)
    return targets
