"""Private Meaning Layer cipher profile commands."""

from __future__ import annotations

import shlex
from pathlib import Path

from core.types import CommandState
from storage import ciphers


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle PML cipher profile commands."""

    del cmd, state
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    if not parts or parts[0] in {"help", "-h", "--help"}:
        _usage()
        return

    action = parts[0]
    try:
        if action == "create" and len(parts) == 2:
            profile = ciphers.create_profile(parts[1])
            print(f"[CIPHER] created {profile['profile']} v{profile['version']}")
            return

        if action == "list":
            profiles = ciphers.list_profiles()
            if not profiles:
                print("[CIPHER] no profiles")
                return
            for profile in profiles:
                print(
                    f" - {profile['profile']} v{profile['version']} "
                    f"({profile['status']}, {len(profile['mapping'])} mappings)"
                )
            return

        if action == "set" and len(parts) == 4:
            profile = ciphers.set_mapping(parts[1], parts[2], parts[3])
            print(f"[CIPHER] set {parts[1]}: {parts[2]} -> {parts[3]}")
            print(f"[CIPHER] fingerprint: {profile['fingerprint']}")
            return

        if action == "unset" and len(parts) == 3:
            profile = ciphers.unset_mapping(parts[1], parts[2])
            print(f"[CIPHER] unset {parts[1]}: {parts[2]}")
            print(f"[CIPHER] fingerprint: {profile['fingerprint']}")
            return

        if action == "show" and len(parts) == 2:
            profile = ciphers.load_profile(parts[1])
            print(f"[CIPHER] {profile['profile']} v{profile['version']} ({profile['status']})")
            print(f"[CIPHER] fingerprint: {profile['fingerprint']}")
            for phrase, code in profile["mapping"].items():
                print(f" - {phrase} -> {code}")
            return

        if action == "fingerprint" and len(parts) == 2:
            profile = ciphers.load_profile(parts[1])
            print(profile["fingerprint"])
            return

        if action == "export" and len(parts) in {2, 3}:
            output = Path(parts[2]) if len(parts) == 3 else None
            path = ciphers.export_profile(parts[1], output)
            print(f"[CIPHER] exported: {path}")
            return

        if action == "import" and len(parts) >= 2:
            _import(parts[1:])
            return

        if action == "rotate" and len(parts) == 2:
            profile = ciphers.rotate_profile(parts[1])
            print(f"[CIPHER] rotated {profile['profile']} to v{profile['version']}")
            print(f"[CIPHER] fingerprint: {profile['fingerprint']}")
            return

        if action == "revoke" and len(parts) in {2, 3}:
            version = int(parts[2]) if len(parts) == 3 else None
            profile = ciphers.revoke_profile(parts[1], version)
            print(f"[CIPHER] revoked {profile['profile']} v{profile['version']}")
            return

        if action == "encode" and len(parts) >= 3:
            encoded, profile = ciphers.encode_text(" ".join(parts[2:]), parts[1])
            print(f"[CIPHER] {profile['profile']} v{profile['version']}: {encoded}")
            return

        if action == "decode" and len(parts) >= 3:
            decoded, ok = ciphers.decode_text(" ".join(parts[2:]), parts[1])
            if not ok:
                print("[CIPHER] profile not found")
                return
            print(f"[CIPHER] {parts[1]}: {decoded}")
            return
    except (FileExistsError, FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"Error: {exc}")
        return

    _usage()


def _import(parts: list[str]) -> None:
    path = Path(parts[0])
    as_profile: str | None = None
    replace = False
    merge = False
    index = 1
    while index < len(parts):
        part = parts[index]
        if part == "--replace":
            replace = True
        elif part == "--merge":
            merge = True
        elif part == "--as" and index + 1 < len(parts):
            as_profile = parts[index + 1]
            index += 1
        else:
            raise ValueError(f"unknown import option: {part}")
        index += 1

    profile = ciphers.import_profile(
        path,
        as_profile=as_profile,
        replace=replace,
        merge=merge,
    )
    print(f"[CIPHER] imported {profile['profile']} v{profile['version']}")
    print(f"[CIPHER] fingerprint: {profile['fingerprint']}")


def _usage() -> None:
    print(
        "Usage: beep cipher "
        "list | create <profile> | set <profile> <phrase> <code> | "
        "unset <profile> <phrase> | show <profile> | export <profile> [path] | "
        "import <path> [--as <profile>] [--replace|--merge] | "
        "rotate <profile> | revoke <profile> [version] | "
        "encode <profile> <text> | decode <profile> <text>"
    )
