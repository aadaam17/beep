"""Configuration file inspection commands."""

from __future__ import annotations

from core.types import CommandState
from storage.app_config import config_search_paths, load_app_config


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle config inspection commands."""

    del cmd, state
    parts = args.strip().split()
    action = parts[0] if parts else "show"

    if action == "path":
        result = load_app_config()
        if result["path"]:
            print(f"[CONFIG] active: {result['path']}")
        else:
            print("[CONFIG] no config file found")
        print("[CONFIG] search paths:")
        for path in config_search_paths():
            print(f" - {path}")
        return

    if action == "validate":
        result = load_app_config()
        if not result["path"]:
            print("[CONFIG] no config file found")
            return
        if result["errors"]:
            print(f"[CONFIG] invalid: {result['path']}")
            for error in result["errors"]:
                print(f" - {error}")
            return
        print(f"[CONFIG] valid: {result['path']}")
        return

    if action == "show":
        result = load_app_config()
        if not result["path"]:
            print("[CONFIG] no config file found")
            print("[CONFIG] create ./beep.toml or ~/.config/beep/config.toml")
            return
        print(f"[CONFIG] active: {result['path']}")
        if result["errors"]:
            print("[CONFIG] errors:")
            for error in result["errors"]:
                print(f" - {error}")
            return
        sections = sorted(result["data"].keys())
        print("[CONFIG] sections: " + (", ".join(sections) if sections else "(empty)"))
        return

    print("Usage: beep config [show|path|validate]")
