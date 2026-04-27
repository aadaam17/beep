import json
from pathlib import Path

from storage.profile import get_user

SESSION_FILE = Path.home() / ".beep" / "beep_session.json"


def load_session():
    if not SESSION_FILE.exists():
        return None

    try:
        session = json.loads(SESSION_FILE.read_text())
    except json.JSONDecodeError:
        return None

    username = session.get("username")
    if not username:
        return None

    user = get_user(username)
    if not user:
        clear_session()
        return None

    return {
        "username": user["username"],
        "pubkey": user["pubkey"],
    }


def save_session(username, pubkey):
    SESSION_FILE.write_text(
        json.dumps(
            {
                "username": username,
                "pubkey": pubkey,
            },
            indent=2,
        )
    )


def clear_session():
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
