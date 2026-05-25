"""Optional relay endpoint management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from network.peers import normalize_peer_url
from storage.network_policy import order_network_targets

RELAY_FILE = Path.home() / ".beep" / "relays.json"
RELAY_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_relays() -> list[str]:
    """Load configured relay endpoints."""

    if not RELAY_FILE.exists():
        return []

    raw = RELAY_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    try:
        relays = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(relays, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for relay in relays:
        if not isinstance(relay, str):
            continue
        try:
            candidate = normalize_peer_url(relay)
        except ValueError:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    if normalized != relays:
        save_relays(normalized)
    return normalized


def save_relays(relays: Iterable[str]) -> None:
    """Persist configured relay endpoints."""

    normalized: list[str] = []
    seen: set[str] = set()
    for relay in relays:
        candidate = normalize_peer_url(relay)
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    RELAY_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def add_relay(relay_url: str) -> str:
    """Add a relay endpoint."""

    relay = normalize_peer_url(relay_url)
    relays = load_relays()
    if relay not in relays:
        relays.append(relay)
    save_relays(relays)
    return relay


def remove_relay(relay_url: str) -> str:
    """Remove a relay endpoint."""

    relay = normalize_peer_url(relay_url)
    relays = [item for item in load_relays() if item != relay]
    save_relays(relays)
    return relay


def load_network_targets() -> list[str]:
    """Return deduplicated direct peers plus relay endpoints."""

    from network.peers import load_peers

    return order_network_targets(load_peers(), load_relays())
