# network/node_manager.py
"""Background local-node lifecycle helpers."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import signal
from pathlib import Path
from typing import TypedDict, cast

import requests

from storage.atomic import atomic_write_json, read_json_with_backup
from storage.network_policy import node_autostart_enabled

RUNTIME_FILE = Path.home() / ".beep" / "node_runtime.json"
NODE_LOG_FILE = Path.home() / ".beep" / "node_runtime.log"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STARTUP_TIMEOUT_SECONDS = 30.0


class NodeRuntimeRecord(TypedDict):
    """Persisted metadata for the local background node."""

    host: str
    port: int
    url: str
    username: str
    pubkey: str
    pid: int


class NodeHealthRecord(TypedDict):
    """Health details reported by a running node."""

    reachable: bool
    objects: int | None
    relay_only_mode: bool | None
    error: str | None


def load_node_runtime() -> NodeRuntimeRecord | None:
    """Load the persisted local node runtime record if valid."""

    raw = read_json_with_backup(RUNTIME_FILE)
    if raw is None:
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

    atomic_write_json(RUNTIME_FILE, record, indent=2)


def clear_node_runtime() -> None:
    """Remove the persisted local node runtime record."""

    try:
        RUNTIME_FILE.unlink()
    except FileNotFoundError:
        pass


def node_log_path() -> Path:
    """Return the background node log path."""

    return NODE_LOG_FILE


def node_log_tail(max_lines: int = 12) -> list[str]:
    """Return the last few node log lines for diagnostics."""

    if not NODE_LOG_FILE.exists():
        return []
    try:
        lines = NODE_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max_lines:]


def stop_background_node() -> bool:
    """Best-effort stop for the persisted background node process."""

    runtime = load_node_runtime()
    clear_node_runtime()
    if runtime is None:
        return False

    try:
        os.kill(runtime["pid"], signal.SIGTERM)
    except OSError:
        return False
    return True


def ensure_background_node(
    username: str,
    pubkey: str,
    *,
    startup_timeout: float | None = None,
) -> NodeRuntimeRecord | None:
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
        runtime = _spawn_background_node(
            username,
            pubkey,
            port,
            startup_timeout=startup_timeout,
        )
        if runtime is not None:
            save_node_runtime(runtime)
            return runtime

    return None


def node_runtime_reachable(runtime: NodeRuntimeRecord | None = None) -> bool:
    """Return whether the tracked node runtime is reachable."""

    record = load_node_runtime() if runtime is None else runtime
    if record is None:
        return False
    return _node_is_reachable(record["url"])


def node_runtime_health(runtime: NodeRuntimeRecord | None = None) -> NodeHealthRecord:
    """Return structured health for the tracked node runtime."""

    record = load_node_runtime() if runtime is None else runtime
    if record is None:
        return {
            "reachable": False,
            "objects": None,
            "relay_only_mode": None,
            "error": "node is not running",
        }
    try:
        response = requests.get(f"{record['url']}/health", timeout=1.5)
        if response.status_code != 200:
            return {
                "reachable": False,
                "objects": None,
                "relay_only_mode": None,
                "error": f"HTTP {response.status_code}",
            }
        payload = response.json()
    except Exception as exc:
        return {
            "reachable": False,
            "objects": None,
            "relay_only_mode": None,
            "error": str(exc),
        }
    objects = payload.get("objects") if isinstance(payload, dict) else None
    relay_only = payload.get("relay_only_mode") if isinstance(payload, dict) else None
    return {
        "reachable": True,
        "objects": objects if isinstance(objects, int) else None,
        "relay_only_mode": relay_only if isinstance(relay_only, bool) else None,
        "error": None,
    }


def _spawn_background_node(
    username: str,
    pubkey: str,
    port: int,
    *,
    startup_timeout: float | None = None,
) -> NodeRuntimeRecord | None:
    """Start a detached local node process and wait for readiness."""

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

    NODE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with NODE_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"starting node on 127.0.0.1:{port}\n"
        )
        log_file.flush()
        try:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                startupinfo=startupinfo,
                close_fds=False if os.name == "nt" else True,
                start_new_session=False if os.name == "nt" else True,
            )
        except OSError as exc:
            log_file.write(f"failed to spawn node process: {exc}\n")
            return None

    runtime: NodeRuntimeRecord = {
        "host": "127.0.0.1",
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "username": username,
        "pubkey": pubkey,
        "pid": process.pid,
    }

    timeout = _startup_timeout_seconds(startup_timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _node_is_reachable(runtime["url"]):
            return runtime
        if process.poll() is not None:
            _append_node_log(
                f"node process exited before readiness "
                f"(code {process.returncode})"
            )
            return None
        time.sleep(0.25)

    _append_node_log(f"node was not reachable after {timeout:.1f}s")

    return None


def _node_is_reachable(base_url: str) -> bool:
    """Return whether the local background node answers health-like requests."""

    try:
        response = requests.get(f"{base_url}/health", timeout=1.0)
    except requests.RequestException:
        return False
    return response.status_code == 200


def _find_free_port() -> int:
    """Allocate an available localhost TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _startup_timeout_seconds(override: float | None) -> float:
    """Return the configured startup timeout for background nodes."""

    if override is not None and override > 0:
        return override
    raw_value = os.environ.get("BEEP_NODE_STARTUP_TIMEOUT")
    if raw_value:
        try:
            value = float(raw_value)
        except ValueError:
            return DEFAULT_STARTUP_TIMEOUT_SECONDS
        if value > 0:
            return value
    return DEFAULT_STARTUP_TIMEOUT_SECONDS


def _append_node_log(message: str) -> None:
    """Append a small diagnostic message to the node log."""

    try:
        NODE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with NODE_LOG_FILE.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
            )
    except OSError:
        pass
