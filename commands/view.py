from core.thread_view import print_focus_view


def dispatch(cmd, args, state):
    obj_id = (args or "").strip()
    if not obj_id:
        print("[VIEW] Usage: view <object_id>")
        return

    print_focus_view(obj_id)
