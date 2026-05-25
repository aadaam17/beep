# network/query.py

"""Peer query helpers."""

from __future__ import annotations

from typing import TypedDict

import requests


class DiscoveredIdentity(TypedDict):
    """Identity information discovered from a peer."""

    username: str
    pubkey: str
    handle: str
    endpoint: str | None
    stale_endpoint: str | None
    presence_state: str
    relay_hints: list[str]


class QueryEngine:
    def __init__(self, peers: list[str]):
        self.peers = peers

    def query_recent(self, limit: int = 50) -> list[str]:
        results: set[str] = set()

        for peer in self.peers:
            try:
                res = requests.get(f"{peer}/objects/recent?limit={limit}", timeout=2)
                ids = res.json().get("objects", [])
                results.update(item for item in ids if isinstance(item, str))
            except Exception:
                continue

        return list(results)

    def query_by_author(self, author: str) -> list[str]:
        results: set[str] = set()

        for peer in self.peers:
            try:
                res = requests.get(f"{peer}/objects/by_author/{author}", timeout=2)
                ids = res.json().get("objects", [])
                results.update(item for item in ids if isinstance(item, str))
            except Exception:
                continue

        return list(results)


def resolve_identity(
    identifier: str,
    peers: list[str],
) -> list[DiscoveredIdentity]:
    """Resolve an identity handle or username through known peers."""

    discovered: dict[str, DiscoveredIdentity] = {}

    for peer in peers:
        try:
            response = requests.get(f"{peer}/resolve/{identifier}", timeout=2)
            if response.status_code != 200:
                continue
            payload = response.json()
        except Exception:
            continue

        matches = payload.get("matches", [])
        if not isinstance(matches, list):
            continue

        for match in matches:
            if not isinstance(match, dict):
                continue
            username = match.get("username")
            pubkey = match.get("pubkey")
            handle = match.get("handle")
            endpoint = match.get("endpoint")
            stale_endpoint = match.get("stale_endpoint")
            presence_state = match.get("presence_state")
            if not isinstance(username, str) or not isinstance(pubkey, str) or not isinstance(handle, str):
                continue
            discovered[pubkey] = {
                "username": username,
                "pubkey": pubkey,
                "handle": handle,
                "endpoint": endpoint if isinstance(endpoint, str) and endpoint else None,
                "stale_endpoint": (
                    stale_endpoint
                    if isinstance(stale_endpoint, str) and stale_endpoint.strip()
                    else None
                ),
                "presence_state": (
                    presence_state
                    if presence_state in {"fresh", "stale", "none"}
                    else "none"
                ),
                "relay_hints": [
                    item
                    for item in match.get("relay_hints", [])
                    if isinstance(item, str)
                ]
                if isinstance(match.get("relay_hints"), list)
                else [],
            }

    return sorted(discovered.values(), key=lambda item: (item["username"], item["pubkey"]))
