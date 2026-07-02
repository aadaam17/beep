"""Configuration file inspection commands."""

from __future__ import annotations

from pathlib import Path

from core.types import CommandState
from storage.app_config import (
    config_search_paths,
    effective_config_summary,
    load_app_config,
    write_default_config,
)


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle config inspection commands."""

    del cmd, state
    parts = args.strip().split()
    action = parts[0] if parts else "show"

    if action == "init":
        target = Path(parts[1]).expanduser() if len(parts) > 1 else None
        try:
            path = write_default_config(target)
        except FileExistsError as exc:
            print(f"[CONFIG] already exists: {exc}")
            return
        except OSError as exc:
            print(f"[CONFIG] could not create config: {exc}")
            return
        print(f"[CONFIG] created: {path}")
        return

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
        if result["warnings"]:
            print(f"[CONFIG] valid with warnings: {result['path']}")
            for warning in result["warnings"]:
                print(f" - {warning}")
            return
        print(f"[CONFIG] valid: {result['path']}")
        return

    if action in {"show", "effective"}:
        result = load_app_config()
        if not result["path"]:
            print("[CONFIG] no config file found")
            print("[CONFIG] create one with: beep config init")
            return
        print(f"[CONFIG] active: {result['path']}")
        if result["errors"]:
            print("[CONFIG] errors:")
            for error in result["errors"]:
                print(f" - {error}")
            return
        if result["warnings"]:
            print("[CONFIG] warnings:")
            for warning in result["warnings"]:
                print(f" - {warning}")
        sections = sorted(result["data"].keys())
        print("[CONFIG] sections: " + (", ".join(sections) if sections else "(empty)"))
        if action == "effective":
            summary = effective_config_summary()
            print("[CONFIG] network policy overrides:")
            overrides = summary["network_policy_overrides"]
            if isinstance(overrides, dict) and overrides:
                for key in sorted(overrides):
                    print(f" - {key}: {overrides[key]}")
            else:
                print(" - (none)")
            print(f"[CONFIG] config peers: {len(summary['peers'])}")
            print(f"[CONFIG] config relays: {len(summary['relays'])}")
        return

    print("Usage: beep config [show|effective|path|validate|init [path]]")
