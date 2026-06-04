"""Atomic local file persistence helpers."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def backup_path(path: Path) -> Path:
    """Return the companion backup path for an atomically managed file."""

    return path.with_name(f"{path.name}.bak")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically by replacing the target after fsync."""

    path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_path(path)
    with _file_lock(path):
        _atomic_replace(path, backup, data)


def _atomic_replace(path: Path, backup: Path, data: bytes) -> None:
    """Write data to a temp file and atomically replace the target."""

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file_handle:
            file_handle.write(data)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        if path.exists():
            path.replace(backup)
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Serialize writes with a small companion lock file."""

    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        if lock_file.tell() == 0 and lock_file.read(1) == b"":
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write text atomically."""

    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    """Write JSON atomically with deterministic key order."""

    atomic_write_text(
        path,
        json.dumps(payload, indent=indent, sort_keys=True),
        encoding="utf-8",
    )


def read_json_with_backup(path: Path, default: Any = None) -> Any:
    """Read JSON, falling back to the companion backup on corruption."""

    for candidate in (path, backup_path(path)):
        if not candidate.exists():
            continue
        try:
            raw = candidate.read_text(encoding="utf-8")
            if not raw.strip():
                return default
            return json.loads(raw)
        except (OSError, ValueError):
            continue
    return default
