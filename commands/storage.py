# commands/storage.py
"""Storage retention and pruning CLI commands."""

from __future__ import annotations

import shlex
from typing import NamedTuple, cast

from core.types import CommandState
from storage.objects import (
    PruneReport,
    RetentionReason,
    RetentionSummary,
    object_retention_reason,
    prune_objects,
    retained_objects,
    retention_summary,
)

VALID_RETENTION_REASONS: tuple[RetentionReason, ...] = (
    "retain",
    "iro",
    "recovery",
    "identity",
    "authored",
    "following",
    "chat_participant",
    "room_participant",
)


class ReasonSelection(NamedTuple):
    """Parsed retention-reason selection state for the storage command."""

    valid: bool
    reason: RetentionReason | None


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle storage inspection and pruning commands."""

    if cmd != "storage":
        return

    parts = shlex.split(args or "")
    if not parts:
        _print_usage()
        return

    action = parts[0]
    if action == "status":
        _dispatch_status(parts[1:])
        return
    if action == "inspect":
        _dispatch_inspect(parts[1:])
        return
    if action == "prune":
        _dispatch_prune(parts[1:])
        return

    _print_usage()


def _dispatch_status(parts: list[str]) -> None:
    """Show retained object counts, optionally filtered by reason."""

    selection = _extract_reason(parts)
    if not selection.valid:
        return

    if selection.reason is None:
        summary: RetentionSummary = retention_summary()
        print("[STORAGE] Retention summary")
        retained_count = sum(summary["retained"].values())
        print(f"Total objects: {summary['total']}")
        print(f"Retained objects: {retained_count}")
        print(f"Prunable objects: {summary['prunable']}")
        if summary["retained"]:
            print("Reasons:")
            for reason_name, count in sorted(summary["retained"].items()):
                print(f" - {reason_name}: {count}")
        return

    object_ids = retained_objects(selection.reason)
    print(
        f"[STORAGE] Retained objects for reason '{selection.reason}': {len(object_ids)}"
    )
    for object_id in object_ids:
        print(f" - {object_id}")


def _dispatch_inspect(parts: list[str]) -> None:
    """Show the retention reason for a single object ID."""

    if len(parts) != 1:
        print("Usage: beep storage inspect <object_id>")
        return

    object_id = parts[0]
    reason = object_retention_reason(object_id)
    if reason is None:
        print(f"[STORAGE] {object_id}: prunable")
        return

    print(f"[STORAGE] {object_id}: retained ({reason})")


def _dispatch_prune(parts: list[str]) -> None:
    """Dry-run or apply pruning for unretained objects."""

    apply_changes = "--apply" in parts
    report: PruneReport = prune_objects(dry_run=not apply_changes)
    action = "Pruned" if apply_changes else "Dry-run prune"
    affected_ids = report["pruned"] if apply_changes else report["prunable"]
    print(f"[STORAGE] {action}: {len(affected_ids)} object(s)")
    if affected_ids:
        print("Object IDs:")
        for object_id in affected_ids:
            print(f" - {object_id}")


def _extract_reason(parts: list[str]) -> ReasonSelection:
    """Extract a retention reason filter from CLI flags."""

    if "--reason" not in parts:
        return ReasonSelection(True, None)

    index = parts.index("--reason") + 1
    if index >= len(parts):
        print(
            "Usage: beep storage status --reason "
            "<retain|iro|recovery|identity|authored|following|chat_participant|room_participant>"
        )
        return ReasonSelection(False, None)

    reason = parts[index]
    if reason not in VALID_RETENTION_REASONS:
        print(
            "Usage: beep storage status --reason "
            "<retain|iro|recovery|identity|authored|following|chat_participant|room_participant>"
        )
        return ReasonSelection(False, None)
    return ReasonSelection(True, cast(RetentionReason, reason))


def _print_usage() -> None:
    """Print storage command usage."""

    print(
        "Usage: beep storage status [--reason <reason>] | "
        "beep storage inspect <object_id> | "
        "beep storage prune [--apply]"
    )
