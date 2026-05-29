# core/thread_view.py
"""Thread rendering helpers for posts and nested comments."""

from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from core.identity import resolve_username
from core.types import BeepObjectRecord
from storage.objects import get_object, query_objects

ChildMap: TypeAlias = dict[str, list[BeepObjectRecord]]


def relative_time(timestamp: float) -> str:
    """Render a compact relative timestamp string."""

    try:
        past = datetime.fromtimestamp(timestamp)
    except (TypeError, ValueError, OSError):
        return ""

    now = datetime.now()
    diff = now - past
    seconds = max(int(diff.total_seconds()), 0)

    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"


def _children_by_parent() -> ChildMap:
    """Build the nested comment lookup map keyed by parent object ID."""

    children: ChildMap = {}
    for obj in query_objects(obj_type="comment"):
        parent_id = _parent_id(obj)
        if parent_id is None:
            continue
        children.setdefault(parent_id, []).append(obj)

    for siblings in children.values():
        siblings.sort(key=_timestamp_key)

    return children


def _timestamp_key(item: BeepObjectRecord) -> float:
    """Return the sort key for thread ordering."""

    return item["timestamp"]


def _format_header(obj: BeepObjectRecord, indent: int = 0) -> str:
    """Render one object header line for a thread view."""

    author = resolve_username(obj["author"]) or obj["author"][:10]
    ts = datetime.fromtimestamp(obj["timestamp"]).strftime("%d.%m.%Y")
    rel = relative_time(obj["timestamp"])
    prefix = "    " * indent
    object_id = obj.get("id", "")

    if obj["type"] == "comment":
        return f"{prefix}: [{rel}] [{author}] - {object_id}: {obj['content']}"

    shared_from = _meta_string(obj, "shared_from")
    if shared_from is not None:
        quote = _meta_bool(obj, "quote")
        label = "Quoted" if quote else "Shared"
        suffix = f": {obj['content']}" if quote else ""
        return f"{prefix}:: {label} [{ts} | {rel}] [{author}] - {object_id}{suffix}"

    return f"{prefix}:: [{ts} | {rel}] [{author}] - {object_id}: {obj['content']}"


def print_thread(root_obj_id: str) -> None:
    """Print a post or comment thread from its root object ID."""

    root = get_object(root_obj_id)
    if root is None:
        print("[VIEW] Object not found.")
        return

    children = _children_by_parent()
    _print_full_tree(root, children, indent=0)


def print_focus_view(obj_id: str) -> None:
    """Print a focused comment path plus its descendants."""

    target = get_object(obj_id)
    if target is None:
        print("[VIEW] Object not found.")
        return

    if target["type"] != "comment":
        print_thread(obj_id)
        return

    path = _ancestor_path(target)
    if not path:
        print_thread(obj_id)
        return

    children = _children_by_parent()
    _print_path_with_descendants(path, children)


def _print_full_tree(obj: BeepObjectRecord, children: ChildMap, indent: int) -> None:
    """Recursively print an object and all descendant comments."""

    print(_format_header(obj, indent=indent))
    _print_embedded_source(obj, indent=indent)
    object_id = obj.get("id")
    if not object_id:
        return
    for child in children.get(object_id, []):
        _print_full_tree(child, children, indent + 1)


def _ancestor_path(comment_obj: BeepObjectRecord) -> list[BeepObjectRecord]:
    """Return the root-to-target path for a nested comment."""

    path: list[BeepObjectRecord] = [comment_obj]
    current = comment_obj

    while current["type"] == "comment":
        parent_id = _parent_id(current)
        if parent_id is None:
            break
        parent = get_object(parent_id)
        if parent is None:
            break
        path.append(parent)
        if parent["type"] != "comment":
            break
        current = parent

    return list(reversed(path))


def _print_path_with_descendants(
    path: list[BeepObjectRecord],
    children: ChildMap,
) -> None:
    """Print the focused ancestor chain plus the target comment's subtree."""

    root = path[0]
    print(_format_header(root, indent=0))
    _print_embedded_source(root, indent=0)

    current_indent = 1
    for node in path[1:]:
        print(_format_header(node, indent=current_indent))
        current_indent += 1

    target = path[-1]
    target_id = target.get("id")
    if not target_id:
        return
    for child in children.get(target_id, []):
        _print_full_tree(child, children, current_indent)


def _parent_id(obj: BeepObjectRecord) -> str | None:
    """Extract a string parent ID from comment metadata."""

    return _meta_string(obj, "parent_id")


def _print_embedded_source(obj: BeepObjectRecord, *, indent: int) -> None:
    """Print the shared or quoted source object as an embedded reference line."""

    shared_from = _meta_string(obj, "shared_from")
    if shared_from is None:
        return

    source = get_object(shared_from)
    if source is None:
        return

    print(_format_header(source, indent=indent + 1))


def _meta_string(obj: BeepObjectRecord, key: str) -> str | None:
    """Extract a string metadata value."""

    value = obj.get("meta", {}).get(key)
    return value if isinstance(value, str) and value else None


def _meta_bool(obj: BeepObjectRecord, key: str) -> bool:
    """Extract a boolean metadata value."""

    return obj.get("meta", {}).get(key) is True
