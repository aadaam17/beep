from datetime import datetime

from core.identity import resolve_username
from storage.objects import get_object, query_objects


def relative_time(timestamp):
    try:
        past = datetime.fromtimestamp(int(timestamp))
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


def _children_by_parent():
    children = {}
    for obj in query_objects(obj_type="comment"):
        parent_id = obj.get("meta", {}).get("parent_id")
        if not parent_id:
            continue
        children.setdefault(parent_id, []).append(obj)

    for siblings in children.values():
        siblings.sort(key=lambda item: item["timestamp"])

    return children


def _format_header(obj, indent=0):
    author = resolve_username(obj["author"])
    ts = datetime.fromtimestamp(obj["timestamp"]).strftime("%d.%m.%Y")
    rel = relative_time(obj["timestamp"])
    prefix = "    " * indent

    if obj["type"] == "comment":
        return f"{prefix}: [{rel}] [{author}] - {obj['id']}: {obj['content']}"

    meta = obj.get("meta", {})
    if meta.get("shared_from"):
        label = "Quoted" if meta.get("quote") else "Shared"
        suffix = f": {obj['content']}" if meta.get("quote") else ""
        return f"{prefix}:: {label} [{ts} | {rel}] [{author}] - {obj['id']}{suffix}"

    return f"{prefix}:: [{ts} | {rel}] [{author}] - {obj['id']}: {obj['content']}"


def print_thread(root_obj_id):
    root = get_object(root_obj_id)
    if not root:
        print("[VIEW] Object not found.")
        return

    children = _children_by_parent()
    _print_full_tree(root, children, indent=0)


def print_focus_view(obj_id):
    target = get_object(obj_id)
    if not target:
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


def _print_full_tree(obj, children, indent):
    print(_format_header(obj, indent=indent))
    for child in children.get(obj["id"], []):
        _print_full_tree(child, children, indent + 1)


def _ancestor_path(comment_obj):
    path = [comment_obj]
    current = comment_obj

    while current.get("type") == "comment":
        parent_id = current.get("meta", {}).get("parent_id")
        if not parent_id:
            break
        parent = get_object(parent_id)
        if not parent:
            break
        path.append(parent)
        if parent["type"] != "comment":
            break
        current = parent

    return list(reversed(path))


def _print_path_with_descendants(path, children):
    root = path[0]
    print(_format_header(root, indent=0))

    current_indent = 1
    for node in path[1:]:
        print(_format_header(node, indent=current_indent))
        current_indent += 1

    target = path[-1]
    for child in children.get(target["id"], []):
        _print_full_tree(child, children, current_indent)
