# commands/restore.py
"""Restore and recovery CLI commands."""

from __future__ import annotations

import getpass
import shlex

from core.types import CommandState
from storage.restore import recover_missing_from_iro, restore_from_file, restore_from_mnemonic


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle restore and recovery commands."""

    if cmd != "restore":
        return

    parts = shlex.split(args or "")
    if not parts:
        print(
            'Usage: restore --file <path> | restore --mnemonic "<phrase>" '
            "[-u <username>] [-p <new-local-password>] | restore recover"
        )
        return

    if parts[0] == "recover":
        _dispatch_recover(state)
        return

    if "--file" in parts:
        _dispatch_restore_file(parts, state)
        return

    if "--mnemonic" in parts:
        _dispatch_restore_mnemonic(parts, state)
        return

    print(
        'Usage: restore --file <path> | restore --mnemonic "<phrase>" '
        "[-u <username>] [-p <new-local-password>] | restore recover"
    )


def _dispatch_restore_file(parts: list[str], state: CommandState) -> None:
    """Restore local node state from an encrypted backup file."""

    try:
        input_path = parts[parts.index("--file") + 1]
    except IndexError:
        print("Usage: restore --file <path>")
        return

    password = _extract_password(parts)
    if password is None:
        password = getpass.getpass("Backup password: ")

    try:
        result = restore_from_file(input_path, password, auto_login=True)
        restored_username = result.get("username")
        if isinstance(restored_username, str):
            state.user = restored_username
        pubkey = result.get("pubkey")
        if isinstance(pubkey, str):
            state.pubkey = pubkey
        print(
            f"[RESTORE] Restored '{result['username']}' "
            f"from backup file."
        )
    except ValueError as exc:
        print(f"[RESTORE] Error: {exc}")


def _dispatch_restore_mnemonic(parts: list[str], state: CommandState) -> None:
    """Restore identity state from a mnemonic phrase."""

    try:
        mnemonic = parts[parts.index("--mnemonic") + 1]
    except IndexError:
        print('Usage: restore --mnemonic "<phrase>" -p <new-local-password>')
        return

    username = None
    if "-u" in parts:
        index = parts.index("-u") + 1
        if index < len(parts):
            username = parts[index]
    elif "--username" in parts:
        index = parts.index("--username") + 1
        if index < len(parts):
            username = parts[index]

    password = _extract_password(parts)
    if password is None:
        password = getpass.getpass("New local password: ")

    try:
        result = restore_from_mnemonic(
            mnemonic,
            local_password=password,
            username=username,
            auto_login=True,
        )
        restored_username = result.get("username")
        restored_pubkey = result.get("pubkey")
        if isinstance(restored_username, str):
            state.user = restored_username
        if isinstance(restored_pubkey, str):
            state.pubkey = restored_pubkey
        print(f"[RESTORE] Restored '{result['username']}' from mnemonic.")
    except ValueError as exc:
        print(f"[RESTORE] Error: {exc}")


def _dispatch_recover(state: CommandState) -> None:
    """Recover missing IRO-indexed objects for the current user."""

    if state.user is None:
        print("[RESTORE] You must be logged in to recover objects.")
        return

    try:
        result = recover_missing_from_iro(state.user, verbose=True)
        print(
            f"[RESTORE] Recovery complete for '{result['username']}' "
            f"with {result['imported']} imported object(s)."
        )
    except ValueError as exc:
        print(f"[RESTORE] Error: {exc}")


def _extract_password(parts: list[str]) -> str | None:
    """Extract an inline password from CLI flags if present."""

    for flag in ("-p", "--password"):
        if flag in parts:
            index = parts.index(flag) + 1
            if index < len(parts):
                return parts[index]
    return None
