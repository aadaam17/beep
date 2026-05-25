"""Identity display and known-user resolution helpers."""

from __future__ import annotations

from core.types import UserRecord
from storage.profile import get_known_users, get_user_by_pubkey

HANDLE_SEPARATOR = "#"
HANDLE_SUFFIX_LENGTH = 6


def resolve_username(pubkey: str) -> str:
    """Resolve a username for display, falling back to a short pubkey."""

    user = get_user_by_pubkey(pubkey)
    if user is not None:
        return user["username"]
    return pubkey[:10]


def handle_suffix(pubkey: str) -> str:
    """Return the short stable handle suffix for a public key."""

    return pubkey[:HANDLE_SUFFIX_LENGTH].lower()


def build_identity_handle(username: str, pubkey: str) -> str:
    """Build the user-facing Beep handle for a known identity."""

    return f"{username}{HANDLE_SEPARATOR}{handle_suffix(pubkey)}"


def find_identity_matches(identifier: str) -> list[UserRecord]:
    """Find known identities that match a username, handle, or public key."""

    lookup = identifier.strip().lower()
    if not lookup:
        return []

    if len(lookup) == 64:
        direct = get_user_by_pubkey(lookup)
        return [direct] if direct is not None else []

    matches: list[UserRecord] = []
    for user in get_known_users():
        username = user["username"].lower()
        user_pubkey = user["pubkey"].lower()
        user_handle = build_identity_handle(username, user_pubkey).lower()

        if lookup == username or lookup == user_handle or lookup == user_pubkey:
            matches.append(user)

    return matches

