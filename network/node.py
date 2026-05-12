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


@app.get("/inventory")
def inventory():
    index = ObjectIndex()
    objs = index.get_all()

    return {
        "ids": [o["id"] for o in objs],
        "meta": {
            o["id"]: {
                "author": o["author"],
                "timestamp": o["timestamp"],
            }
            for o in objs
        },
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


def _watch_session(username, pubkey):
    while True:
        time.sleep(1)
        if not session_matches(username, pubkey):
            print("[NODE] Session ended or changed. Stopping node.")
            os._exit(0)


def run_node(host="0.0.0.0", port=8000, session_username=None, session_pubkey=None):
    if session_username and session_pubkey:
        watcher = threading.Thread(
            target=_watch_session,
            args=(session_username, session_pubkey),
            daemon=True,
        )
        watcher.start()
    uvicorn.run(app, host=host, port=port)
