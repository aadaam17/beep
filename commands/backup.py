# commands/backup.py
"""Backup-related CLI commands."""

from __future__ import annotations

import getpass
import shlex

from core.types import CommandState
from storage.backup import create_backup_file, create_mnemonic, import_backup_file


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle backup creation and import commands."""

    if cmd != "backup":
        return

    parts = shlex.split(args or "")
    if not parts:
        print(
            "Usage: backup create --file <path> | backup create --mnemonic | "
            "backup import --file <path>"
        )
        return

    action = parts[0]
    if action == "create":
        _dispatch_create(parts[1:], state)
        return
    if action == "import":
        _dispatch_import(parts[1:])
        return

    print(
        "Usage: backup create --file <path> | backup create --mnemonic | "
        "backup import --file <path>"
    )


def _dispatch_create(parts: list[str], state: CommandState) -> None:
    """Create a backup file or mnemonic phrase."""

    if state.user is None:
        print("[BACKUP] You must be logged in to create a backup.")
        return

    if "--mnemonic" in parts:
        phrase = create_mnemonic(state.user)
        print("[BACKUP] Mnemonic recovery phrase:")
        print(phrase)
        return

    if "--file" not in parts:
        print("Usage: backup create --file <path> | backup create --mnemonic")
        return

    try:
        output_path = parts[parts.index("--file") + 1]
    except IndexError:
        print("Usage: backup create --file <path>")
        return

    password = _extract_password(parts)
    if password is None:
        password = getpass.getpass("Backup password: ")

    try:
        output = create_backup_file(state.user, output_path, password)
        print(f"[BACKUP] Created encrypted backup: {output}")
    except ValueError as exc:
        print(f"[BACKUP] Error: {exc}")


def _dispatch_import(parts: list[str]) -> None:
    """Import an encrypted backup file into local storage."""

    if "--file" not in parts:
        print("Usage: backup import --file <path>")
        return

    try:
        input_path = parts[parts.index("--file") + 1]
    except IndexError:
        print("Usage: backup import --file <path>")
        return

    password = _extract_password(parts)
    if password is None:
        password = getpass.getpass("Backup password: ")

    try:
        result = import_backup_file(input_path, password)
        print(
            f"[BACKUP] Imported backup for '{result['username']}' "
            f"with {result['imported_objects']} object(s)."
        )
    except ValueError as exc:
        print(f"[BACKUP] Error: {exc}")


def _extract_password(parts: list[str]) -> str | None:
    """Extract an inline password from CLI flags if present."""

    for flag in ("-p", "--password"):
        if flag in parts:
            index = parts.index(flag) + 1
            if index < len(parts):
                return parts[index]
    return None
