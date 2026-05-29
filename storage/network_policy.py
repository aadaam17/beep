# storage/network_policy.py
"""Persistent network policy for relay and node behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict, cast

NetworkStrategy = Literal["prefer-direct", "direct-only", "relay-first"]


class NetworkPolicy(TypedDict):
    """Runtime network policy settings."""

    relay_enabled: bool
    node_autostart: bool
    strategy: NetworkStrategy
    presence_ttl_seconds: int
    presence_refresh_seconds: int
    public_endpoint: str


POLICY_FILE = Path.home() / ".beep" / "network_policy.json"
DEFAULT_POLICY: NetworkPolicy = {
    "relay_enabled": True,
    "node_autostart": True,
    "strategy": "prefer-direct",
    "presence_ttl_seconds": 24 * 60 * 60,
    "presence_refresh_seconds": 15 * 60,
    "public_endpoint": "",
}


def load_network_policy() -> NetworkPolicy:
    """Load the saved network policy or return sane defaults."""

    if not POLICY_FILE.exists():
        return dict(DEFAULT_POLICY)

    try:
        raw = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
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

    return policy


def save_network_policy(policy: NetworkPolicy) -> None:
    """Persist a full network policy."""

    POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    POLICY_FILE.write_text(json.dumps(policy, indent=2), encoding="utf-8")


def update_network_policy(**changes: object) -> NetworkPolicy:
    """Apply validated updates to the saved network policy."""

    policy = load_network_policy()

    relay_enabled = changes.get("relay_enabled")
    if isinstance(relay_enabled, bool):
        policy["relay_enabled"] = relay_enabled

    node_autostart = changes.get("node_autostart")
    if isinstance(node_autostart, bool):
        policy["node_autostart"] = node_autostart

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
