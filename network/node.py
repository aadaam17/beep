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
from storage.network_policy import load_network_policy, presence_refresh_seconds
from storage.objects import list_objects, prune_objects
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
_POST_WINDOWS: dict[str, deque[float]] = defaultdict(deque)
_OBJECTS_BY_IP: dict[str, int] = defaultdict(int)
DEFAULT_INVENTORY_LIMIT = 100
MAX_INVENTORY_LIMIT = 500


@app.get("/health")
def health() -> dict[str, Any]:
    """Return node health and policy-relevant runtime limits."""

    return {
        "status": "ok",
        "objects": len(store.list_ids()),
        "max_object_bytes": _policy_int("max_object_bytes"),
        "max_posts_per_minute": _policy_int("max_posts_per_minute"),
        "relay_only_mode": load_network_policy()["relay_only_mode"],
        "time": time.time(),
    }


@app.get("/objects")
def list_objects_route(request: Request):
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
    return {"objects": store.list_ids()}


@app.get("/object/{obj_id}")
def get_object(obj_id: str, request: Request):
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
    obj = store.get(obj_id)
    if not obj:
        return {"error": "not found"}
    return obj


@app.post("/object")
async def receive_object_route(request: Request):
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)

    if not _request_allowed(request):
        return JSONResponse({"error": "rate limited"}, status_code=429)

    max_object_bytes = _policy_int("max_object_bytes")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_object_bytes:
                return JSONResponse({"error": "payload too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"error": "invalid content length"}, status_code=400)

    body = await request.body()
    if len(body) > max_object_bytes:
        return JSONResponse({"error": "payload too large"}, status_code=413)

    try:
        obj = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    if not isinstance(obj, dict) or not obj:
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    policy_error = _relay_policy_error(request, obj)
    if policy_error is not None:
        message, status_code = policy_error
        return JSONResponse({"error": message}, status_code=status_code)

    ok = handle_incoming_object(obj)
    if not ok:
        return JSONResponse({"status": "rejected"}, status_code=403)

    _track_accepted_object(request, obj)
    return {"status": "accepted"}


def _request_allowed(request: Request) -> bool:
    """Apply a small in-memory POST rate limit per remote host."""

    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _POST_WINDOWS[client]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= _policy_int("max_posts_per_minute"):
        return False
    window.append(now)
    return True


def _auth_allowed(request: Request) -> bool:
    """Return whether the request satisfies private peer auth settings."""

    policy = load_network_policy()
    if not policy["peer_auth_required"]:
        return True
    token = policy["peer_auth_token"].strip()
    if not token:
        return False
    return request.headers.get("X-Beep-Peer-Token") == token


def _relay_policy_error(
    request: Request,
    obj: dict[str, object],
) -> tuple[str, int] | None:
    """Return a policy error for an incoming relay object, if any."""

    policy = load_network_policy()
    client = request.client.host if request.client else "unknown"
    author = obj.get("author")
    if isinstance(author, str) and author in policy["denylisted_authors"]:
        return ("author denied", 403)
    if client in policy["denylisted_ips"]:
        return ("ip denied", 403)
    if len(list_objects()) >= policy["relay_retention_limit"]:
        prune_objects(dry_run=False)
        if len(list_objects()) >= policy["relay_retention_limit"]:
            return ("relay retention limit reached", 507)
    if isinstance(author, str) and _author_object_count(author) >= policy["max_objects_per_author"]:
        return ("author object quota reached", 429)
    if _OBJECTS_BY_IP[client] >= policy["max_objects_per_ip"]:
        return ("ip object quota reached", 429)
    return None


def _track_accepted_object(request: Request, obj: dict[str, object]) -> None:
    """Track lightweight accepted-object counters for server-side quotas."""

    client = request.client.host if request.client else "unknown"
    _OBJECTS_BY_IP[client] += 1


def _author_object_count(author: str) -> int:
    """Count stored objects by author."""

    index = ObjectIndex()
    return len(index.get_by_author(author))


def _policy_int(key: str) -> int:
    """Read an integer node policy value."""

    return int(load_network_policy()[key])


@app.get("/inventory")
def inventory(
    request: Request,
    cursor: str | None = None,
    limit: int = DEFAULT_INVENTORY_LIMIT,
    since: float | None = None,
) -> dict[str, Any]:
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
    index = ObjectIndex()
    objs = sorted(index.get_all(), key=lambda obj: (obj["timestamp"], obj["id"]))
    if since is not None:
        objs = [obj for obj in objs if obj["timestamp"] > since]

    start = 0
    if cursor:
        for position, obj in enumerate(objs):
            if obj.get("id") == cursor:
                start = position + 1
                break

    bounded_limit = max(1, min(limit, MAX_INVENTORY_LIMIT))
    page = objs[start : start + bounded_limit]
    next_cursor = page[-1]["id"] if start + bounded_limit < len(objs) and page else None

    ids: list[str] = []
    meta: dict[str, dict[str, Any]] = {}

    for o in page:
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
        "next_cursor": next_cursor,
        "limit": bounded_limit,
        "remaining": max(0, len(objs) - (start + len(page))),
    }


@app.get("/objects/by_author/{author}")
def objects_by_author(author: str, request: Request):
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
    index = ObjectIndex()
    return {"objects": index.get_by_author(author)}


@app.get("/objects/by_type/{type_}")
def objects_by_type(type_: str, request: Request):
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
    index = ObjectIndex()
    return {"objects": index.get_by_type(type_)}


@app.get("/objects/recent")
def objects_recent(request: Request, limit: int = 50):
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
    index = ObjectIndex()
    return {"objects": index.get_recent(limit)}


@app.get("/resolve/{identifier}")
def resolve_identity_route(
    identifier: str,
    request: Request,
) -> dict[str, list[dict[str, object]]] | JSONResponse:
    if not _auth_allowed(request):
        return JSONResponse({"error": "unauthorized peer"}, status_code=401)
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
            if not load_network_policy()["relay_only_mode"]:
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
