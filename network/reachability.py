"""Shared endpoint reachability probes."""

from __future__ import annotations

from typing import Literal

import requests

from network.peers import normalize_peer_url

ReachabilityStatus = Literal["reachable", "unreachable"]


def probe_endpoint(target: str) -> ReachabilityStatus:
    """Return whether an HTTP Beep node endpoint responds successfully."""

    try:
        normalized = normalize_peer_url(target)
        response = requests.get(f"{normalized}/objects", timeout=2)
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                return "reachable"
    except Exception:
        return "unreachable"
    return "unreachable"
