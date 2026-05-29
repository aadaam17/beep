# network/node_manager.py
"""Background local-node lifecycle helpers."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict, cast

import requests

from storage.network_policy import node_autostart_enabled

RUNTIME_FILE = Path.home() / ".beep" / "node_runtime.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class NodeRuntimeRecord(TypedDict):
    """Persisted metadata for the local background node."""

    host: str
    port: int
    url: str
    username: str
    pubkey: str
    pid: int


def load_node_runtime() -> NodeRuntimeRecord | None:
    """Load the persisted local node runtime record if valid."""

    if not RUNTIME_FILE.exists():
        return None

    try:
        raw = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if not isinstance(raw, dict):
        return None

    record = cast(dict[str, object], raw)
    host = record.get("host")
    port = record.get("port")
    url = record.get("url")
    username = record.get("username")
    pubkey = record.get("pubkey")
    pid = record.get("pid")

    if not isinstance(host, str) or not host:
        return None
    if not isinstance(port, int) or port <= 0:
        return None
    if not isinstance(url, str) or not url:
        return None
    if not isinstance(username, str) or not username:
        return None
    if not isinstance(pubkey, str) or not pubkey:
        return None
    if not isinstance(pid, int) or pid <= 0:
        return None

    return {
        "host": host,
        "port": port,
        "url": url,
        "username": username,
        "pubkey": pubkey,
        "pid": pid,
    }


def save_node_runtime(record: NodeRuntimeRecord) -> None:
    """Persist the active local node runtime record."""

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")


def clear_node_runtime() -> None:
    """Remove the persisted local node runtime record."""

    try:
        RUNTIME_FILE.unlink()
    except FileNotFoundError:
        pass


def ensure_background_node(username: str, pubkey: str) -> NodeRuntimeRecord | None:
    """Ensure a silent local background node is running for the active session."""

    if not node_autostart_enabled():
        return None

    existing = load_node_runtime()
    if (
        existing is not None
        and existing["username"] == username
        and existing["pubkey"] == pubkey
        and _node_is_reachable(existing["url"])
    ):
        return existing

    preferred_port = (
        existing["port"]
        if existing is not None
        and existing["username"] == username
        and existing["pubkey"] == pubkey
        else None
    )
    clear_node_runtime()

    for attempt in range(3):
        port = (
            preferred_port
            if attempt == 0 and preferred_port is not None
            else _find_free_port()
        )
        runtime = _spawn_background_node(username, pubkey, port)
        if runtime is not None:
            save_node_runtime(runtime)
            return runtime

    return None


def _spawn_background_node(
    username: str,
    pubkey: str,
    port: int,
) -> NodeRuntimeRecord | None:
    """Start a detached local node process and wait briefly for readiness."""

    command = [
        sys.executable,
        "-m",
        "network.node",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--session-username",
        username,
        "--session-pubkey",
        pubkey,
        "--quiet",
    ]

    creationflags = 0
    startupinfo: subprocess.STARTUPINFO | None = None
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
        close_fds=False if os.name == "nt" else True,
    )

    runtime: NodeRuntimeRecord = {
        "host": "127.0.0.1",
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "username": username,
        "pubkey": pubkey,
        "pid": process.pid,
    }

    for _ in range(20):
        if _node_is_reachable(runtime["url"]):
            return runtime
        if process.poll() is not None:
            return None
        time.sleep(0.1)

    return None


def _node_is_reachable(base_url: str) -> bool:
    """Return whether the local background node answers health-like requests."""

    try:
        response = requests.get(f"{base_url}/objects", timeout=0.5)
    except requests.RequestException:
        return False
    return response.status_code == 200


def _find_free_port() -> int:
    """Allocate an available localhost TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])
