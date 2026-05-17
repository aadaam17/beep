# storage/session.py
"""Persistent CLI session helpers."""

from __future__ import annotations

import json
from pathlib import Path

from core.types import SessionRecord
from typing import cast, Any

# Backward-compatible paths
OLD_SESSION_FILE = Path.home() / ".beep" / "beep_session.json"
SESSION_FILE = Path.home() / ".beep" / "session.json"


def _resolve_session_file() -> Path:
    """Prefer new session file, but fall back to old one if needed."""
    if SESSION_FILE.exists():
        return SESSION_FILE
    if OLD_SESSION_FILE.exists():
        return OLD_SESSION_FILE
    return SESSION_FILE


def load_session() -> SessionRecord | None:
    """Load the persisted session if it exists and is well formed."""

    path = _resolve_session_file()

    if not path.exists():
        return None

    try:
        raw_session = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if not isinstance(raw_session, dict):
        return None
    raw_session = cast(dict[str, Any], raw_session)

    username = raw_session.get("username")
    pubkey = raw_session.get("pubkey")

    if not isinstance(username, str) or not username:
        return None
    if not isinstance(pubkey, str) or not pubkey:
        return None

    return {"username": username, "pubkey": pubkey}


def session_matches(username: str, pubkey: str) -> bool:
    """Check whether the persisted session matches the provided identity."""

    session = load_session()

    return (
        session is not None
        and session.get("username") == username
        and session.get("pubkey") == pubkey
    )


def save_session(username: str, pubkey: str) -> None:
    """Persist the active login session (writes to new format only)."""

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    payload: SessionRecord = {
        "username": username,
        "pubkey": pubkey,
    }

    SESSION_FILE.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def clear_session() -> None:
    """Remove both old and new session files if they exist."""

    for path in (SESSION_FILE, OLD_SESSION_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
