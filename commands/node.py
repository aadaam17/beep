from node.runtime import run_node

def dispatch(cmd, args, state):
    if cmd != "node":
        return

    parts = args.split()

    port = 8000
    host = "127.0.0.1"

    if "--port" in parts:
        i = parts.index("--port")
        port = int(parts[i + 1])

    if "--host" in parts:
        i = parts.index("--host")
        host = parts[i + 1]

    run_node(host, port)