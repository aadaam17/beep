# network/node.py
"""Core local node server implementation."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.index import ObjectIndex
from core.identity import build_identity_handle, find_identity_matches
from core.object_store import ObjectStore
from network.sync import receive_object as handle_incoming_object
from storage.network_policy import presence_refresh_seconds
from storage.presence import (
    get_latest_known_endpoint,
    get_latest_presence,
    get_presence_endpoint,
    get_presence_state,
    publish_local_presence,
)
from storage.profile import get_known_users
from storage.session import session_matches

app = FastAPI()
store = ObjectStore()
MAX_OBJECT_BYTES = int(os.getenv("BEEP_MAX_OBJECT_BYTES", str(256 * 1024)))
MAX_POSTS_PER_MINUTE = int(os.getenv("BEEP_MAX_POSTS_PER_MINUTE", "60"))
_POST_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


@app.get("/objects")
def list_objects():
    return {"objects": store.list_ids()}


@app.get("/object/{obj_id}")
def get_object(obj_id: str):
    obj = store.get(obj_id)
    if not obj:
        return {"error": "not found"}
    return obj


@app.post("/object")
async def receive_object_route(request: Request):
    if not _request_allowed(request):
        return JSONResponse({"error": "rate limited"}, status_code=429)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_OBJECT_BYTES:
                return JSONResponse({"error": "payload too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"error": "invalid content length"}, status_code=400)

    body = await request.body()
    if len(body) > MAX_OBJECT_BYTES:
        return JSONResponse({"error": "payload too large"}, status_code=413)

    try:
        obj = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    if not isinstance(obj, dict) or not obj:
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    ok = handle_incoming_object(obj)
    if not ok:
        return JSONResponse({"status": "rejected"}, status_code=403)

    return {"status": "accepted"}


def _request_allowed(request: Request) -> bool:
    """Apply a small in-memory POST rate limit per remote host."""

    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _POST_WINDOWS[client]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= MAX_POSTS_PER_MINUTE:
        return False
    window.append(now)
    return True


# @app.get("/inventory")
# def inventory():
#     index = ObjectIndex()
#     objs = index.get_all()

#     return {
#         "ids": [o["id"] for o in objs],
#         "meta": {
#             o["id"]: {
#                 "author": o["author"],
#                 "timestamp": o["timestamp"],
#             }
#             for o in objs
#         },
#     }


@app.get("/inventory")
def inventory() -> dict[str, Any]:
    index = ObjectIndex()
    objs = index.get_all()

    ids: list[str] = []
    meta: dict[str, dict[str, Any]] = {}

    for o in objs:
        obj_id = o.get("id")
        if not obj_id:
            continue

        ids.append(obj_id)
        meta[obj_id] = {
            "author": o["author"],
            "timestamp": o["timestamp"],
        }

    return {
        "ids": ids,
        "meta": meta,
    }


@app.get("/objects/by_author/{author}")
def objects_by_author(author: str):
    index = ObjectIndex()
    return {"objects": index.get_by_author(author)}


@app.get("/objects/by_type/{type_}")
def objects_by_type(type_: str):
    index = ObjectIndex()
    return {"objects": index.get_by_type(type_)}


@app.get("/objects/recent")
def objects_recent(limit: int = 50):
    index = ObjectIndex()
    return {"objects": index.get_recent(limit)}


@app.get("/resolve/{identifier}")
def resolve_identity_route(identifier: str) -> dict[str, list[dict[str, object]]]:
    matches = find_identity_matches(identifier)
    if not matches and identifier:
        lowered = identifier.lower()
        for user in get_known_users():
            if user["username"].lower() == lowered:
                matches.append(user)

    resolved: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for user in matches:
        if user["pubkey"] in seen:
            continue
        seen.add(user["pubkey"])
        resolved.append(
            {
                "username": user["username"],
                "pubkey": user["pubkey"],
                "handle": build_identity_handle(user["username"], user["pubkey"]),
                "endpoint": get_presence_endpoint(user["pubkey"]),
                "stale_endpoint": get_latest_known_endpoint(user["pubkey"]),
                "presence_state": get_presence_state(user["pubkey"]),
                "relay_hints": _presence_relay_hints(user["pubkey"]),
            }
        )
    return {"matches": resolved}


def _presence_relay_hints(pubkey: str) -> list[str]:
    """Extract relay hints from the latest fresh presence, if any."""

    presence = get_latest_presence(pubkey)
    if presence is None:
        return []
    relay_hints = presence["meta"].get("relay_hints")
    if not isinstance(relay_hints, list):
        return []
    return [item for item in relay_hints if isinstance(item, str)]


def _watch_session(username: str, pubkey: str) -> None:
    while True:
        time.sleep(1)
        if not session_matches(username, pubkey):
            print("[NODE] Session ended or changed. Stopping node.")
            os._exit(0)


def _refresh_presence(username: str, endpoint: str, pubkey: str) -> None:
    """Republish fresh presence while the owning session stays active."""

    while True:
        try:
            publish_local_presence(username, endpoint)
        except Exception:
            pass

        interval = max(30, presence_refresh_seconds())
        for _ in range(interval):
            time.sleep(1)
            if not session_matches(username, pubkey):
                return


def run_node(
    host: str = "0.0.0.0",
    port: int = 8000,
    session_username: str | None = None,
    session_pubkey: str | None = None,
    *,
    quiet: bool = False,
) -> None:
    if session_username is not None and session_pubkey is not None:
        watcher = threading.Thread(
            target=_watch_session,
            args=(session_username, session_pubkey),
            daemon=True,
        )
        watcher.start()
        heartbeat = threading.Thread(
            target=_refresh_presence,
            args=(session_username, f"http://{host}:{port}", session_pubkey),
            daemon=True,
        )
        heartbeat.start()
    uvicorn.run(
        app,
        host=host,
        port=port,
        access_log=not quiet,
        log_level="warning" if quiet else "info",
    )


def main() -> None:
    """Run the node server from the command line."""

    parser = argparse.ArgumentParser(description="Run a Beep node.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--session-username")
    parser.add_argument("--session-pubkey")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    run_node(
        host=args.host,
        port=args.port,
        session_username=args.session_username,
        session_pubkey=args.session_pubkey,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
