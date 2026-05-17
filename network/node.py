# network/node.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import threading
import time
import uvicorn

from core.index import ObjectIndex
from core.object_store import ObjectStore
from network.sync import receive_object as handle_incoming_object
from storage.session import session_matches

from typing import Optional, Any

app = FastAPI()
store = ObjectStore()


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
    obj = await request.json()

    if not obj:
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    ok = handle_incoming_object(obj)
    if not ok:
        return JSONResponse({"status": "rejected"}, status_code=403)

    return {"status": "accepted"}


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


def _watch_session(username: str, pubkey: str) -> None:
    while True:
        time.sleep(1)
        if not session_matches(username, pubkey):
            print("[NODE] Session ended or changed. Stopping node.")
            os._exit(0)


def run_node(
    host: str = "0.0.0.0",
    port: int = 8000,
    session_username: Optional[str] = None,
    session_pubkey: Optional[str] = None,
) -> None:
    if session_username is not None and session_pubkey is not None:
        watcher = threading.Thread(
            target=_watch_session,
            args=(session_username, session_pubkey),
            daemon=True,
        )
        watcher.start()
    uvicorn.run(app, host=host, port=port)
