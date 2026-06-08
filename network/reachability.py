# network/reachability.py
"""Shared endpoint reachability probes."""

from __future__ import annotations

from typing import Literal, TypedDict

import requests

from network.peers import normalize_peer_url
from storage.network_policy import peer_auth_header

ReachabilityStatus = Literal["reachable", "unreachable"]


class EndpointHealth(TypedDict):
    """Health probe result for a node endpoint."""

    status: ReachabilityStatus
    endpoint: str
    objects: int | None
    relay_only_mode: bool | None
    error: str | None


def probe_endpoint(target: str) -> ReachabilityStatus:
    """Return whether an HTTP Beep node endpoint responds successfully."""

    return probe_endpoint_health(target)["status"]


def probe_endpoint_health(target: str) -> EndpointHealth:
    """Return structured health details for an HTTP Beep node endpoint."""

    try:
        normalized = normalize_peer_url(target)
        response = requests.get(f"{normalized}/health", timeout=2)
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                objects = payload.get("objects")
                relay_only = payload.get("relay_only_mode")
                return {
                    "status": "reachable",
                    "endpoint": normalized,
                    "objects": objects if isinstance(objects, int) else None,
                    "relay_only_mode": relay_only if isinstance(relay_only, bool) else None,
                    "error": None,
                }
        fallback = requests.get(
            f"{normalized}/objects",
            headers=peer_auth_header(),
            timeout=2,
        )
        if fallback.status_code == 200 and isinstance(fallback.json(), dict):
            return {
                "status": "reachable",
                "endpoint": normalized,
                "objects": None,
                "relay_only_mode": None,
                "error": None,
            }
    except Exception as exc:
        return {
            "status": "unreachable",
            "endpoint": target,
            "objects": None,
            "relay_only_mode": None,
            "error": str(exc),
        }
    return {
        "status": "unreachable",
        "endpoint": target,
        "objects": None,
        "relay_only_mode": None,
        "error": "endpoint did not return a Beep health response",
    }
