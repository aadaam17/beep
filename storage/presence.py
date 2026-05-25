# storage/presence.py
"""Runtime presence publication and lookup helpers."""

from __future__ import annotations

import time
from typing import cast

from core.object import BeepObject
from core.types import BeepObjectRecord, ObjectMeta
from network.peers import normalize_peer_url
from storage.network_policy import presence_ttl_seconds, public_endpoint
from storage.objects import query_objects, save_object
from storage.profile import get_user
from storage.relay import load_relays

DEFAULT_PRESENCE_TTL_SECONDS = 24 * 60 * 60


def publish_local_presence(
    username: str,
    endpoint: str,
    *,
    ttl_seconds: int | None = None,
) -> str | None:
    """Publish the current reachable endpoint for a local user."""

    user = get_user(username)
    if user is None:
        raise ValueError(f"User '{username}' not found")

    advertised_endpoint = public_endpoint() or endpoint
    try:
        advertised_endpoint = normalize_peer_url(advertised_endpoint)
    except ValueError:
        advertised_endpoint = endpoint

    effective_ttl = (
        ttl_seconds
        if isinstance(ttl_seconds, int) and ttl_seconds > 0
        else presence_ttl_seconds()
    )

    obj = BeepObject.create_object(
        type_="presence",
        author_pubkey=user["pubkey"],
        content=user["username"],
        meta=cast(
            ObjectMeta,
            {
                "username": user["username"],
                "endpoint": advertised_endpoint,
                "reachable_via": "direct+relay" if load_relays() else "direct",
                "relay_hints": load_relays(),
                "ttl": effective_ttl,
            },
        ),
    )
    save_object(obj.to_dict())
    return obj.id


def get_latest_presence(
    pubkey: str,
    *,
    fresh_only: bool = True,
) -> BeepObjectRecord | None:
    """Return the newest known presence object for a public key."""

    presences = [
        obj
        for obj in query_objects(obj_type="presence")
        if obj["author"] == pubkey
    ]
    if fresh_only:
        presences = [obj for obj in presences if is_presence_fresh(obj)]
    if not presences:
        return None
    return max(presences, key=lambda obj: (obj["timestamp"], obj["id"]))


def get_presence_endpoint(pubkey: str) -> str | None:
    """Return the latest known endpoint for a public key."""

    presence = get_latest_presence(pubkey)
    if presence is None:
        return None
    endpoint = presence["meta"].get("endpoint")
    return endpoint if isinstance(endpoint, str) and endpoint else None


def get_latest_known_presence(pubkey: str) -> BeepObjectRecord | None:
    """Return the newest presence object even if it is stale."""

    return get_latest_presence(pubkey, fresh_only=False)


def get_latest_known_endpoint(pubkey: str) -> str | None:
    """Return the latest known endpoint even if its presence is stale."""

    presence = get_latest_known_presence(pubkey)
    if presence is None:
        return None
    endpoint = presence["meta"].get("endpoint")
    return endpoint if isinstance(endpoint, str) and endpoint else None


def get_presence_state(pubkey: str) -> str:
    """Return whether a public key has fresh, stale, or no presence."""

    fresh = get_latest_presence(pubkey)
    if fresh is not None:
        return "fresh"
    stale = get_latest_known_presence(pubkey)
    if stale is not None:
        return "stale"
    return "none"


def is_presence_fresh(
    presence: BeepObjectRecord,
    *,
    now: float | None = None,
) -> bool:
    """Return whether a presence object should still be treated as live."""

    ttl = presence["meta"].get("ttl")
    if not isinstance(ttl, int) or ttl <= 0:
        ttl = DEFAULT_PRESENCE_TTL_SECONDS

    current_time = time.time() if now is None else now
    return (presence["timestamp"] + ttl) > current_time
