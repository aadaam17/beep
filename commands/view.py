"""Object thread viewing commands."""

from core.thread_view import print_focus_view
from core.types import CommandState


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    obj_id = (args or "").strip()
    if not obj_id:
        print("[VIEW] Usage: view <object_id>")
        return

    print_focus_view(obj_id)
