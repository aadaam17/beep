"""Reset local Beep development storage.

This script is intentionally explicit because Beep stores several kinds of
local state outside the main object store. By default it clears identity,
objects, keys, ciphers, peers, relays, and network policy, but it leaves
operator config files in place.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

BEEP_HOME = Path.home() / ".beep"
STORAGE_DIR = BEEP_HOME / "beep_storage"
CONFIG_DIR = Path.home() / ".config" / "beep"

STORAGE_SUBFOLDERS = [
    "users",
    "profiles",
    "posts",
    "rooms",
    "chats",
    "objects",
    "signing",
    "seeds",
]
TOP_LEVEL_DIRS = [
    BEEP_HOME / "ciphers",
]
TOP_LEVEL_FILES = [
    BEEP_HOME / "peers.json",
    BEEP_HOME / "relays.json",
    BEEP_HOME / "network_policy.json",
]
CONFIG_FILES = [
    BEEP_HOME / "config.toml",
    CONFIG_DIR / "config.toml",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset local Beep storage.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--include-config",
        action="store_true",
        help="Also remove ~/.beep/config.toml and ~/.config/beep/config.toml.",
    )
    parser.add_argument(
        "--no-recreate",
        action="store_true",
        help="Do not recreate the main storage subfolders after deletion.",
    )
    args = parser.parse_args()

    targets = _reset_targets(include_config=args.include_config)
    if args.dry_run:
        print("[RESET] Dry run. Would remove:")
        for target in targets:
            print(f" - {target}")
        return

    removed: list[Path] = []
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(target)
        elif target.exists():
            target.unlink()
            removed.append(target)

    if not args.no_recreate:
        for subfolder in STORAGE_SUBFOLDERS:
            (STORAGE_DIR / subfolder).mkdir(parents=True, exist_ok=True)

    print("[RESET] Removed:")
    for target in removed:
        print(f" - {target}")
    if not removed:
        print(" - nothing")

    if not args.no_recreate:
        print("[RESET] Fresh storage folders:")
        for subfolder in STORAGE_SUBFOLDERS:
            print(f" - {STORAGE_DIR / subfolder}")


def _reset_targets(*, include_config: bool) -> list[Path]:
    targets = [STORAGE_DIR / subfolder for subfolder in STORAGE_SUBFOLDERS]
    targets.extend(TOP_LEVEL_DIRS)
    targets.extend(TOP_LEVEL_FILES)
    if include_config:
        targets.extend(CONFIG_FILES)
    return targets


if __name__ == "__main__":
    main()
