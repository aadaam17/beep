"""Lightweight host capability checks for optional node mode."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import socket
import sys
from dataclasses import dataclass


MIN_RECOMMENDED_CPUS = 2
MIN_RECOMMENDED_MEMORY_BYTES = 2 * 1024 * 1024 * 1024
MIN_RECOMMENDED_FREE_STORAGE_BYTES = 1024 * 1024 * 1024
MIN_RECOMMENDED_PYTHON = (3, 11)


@dataclass(frozen=True)
class NodeCapability:
    """Result of a node-mode suitability check."""

    recommended: bool
    can_override: bool
    server_dependencies_installed: bool
    reasons: list[str]


def detect_node_capability() -> NodeCapability:
    """Return whether this device looks suitable for node hosting."""

    reasons: list[str] = []

    if _is_mobile_environment():
        reasons.append("mobile or Termux-style environment detected")

    if sys.version_info < MIN_RECOMMENDED_PYTHON:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        reasons.append(f"Python {version} detected; Python 3.11+ is recommended")

    cpu_count = os.cpu_count() or 0
    if cpu_count and cpu_count < MIN_RECOMMENDED_CPUS:
        reasons.append(f"only {cpu_count} CPU core(s) detected")
    elif cpu_count == 0:
        reasons.append("CPU count could not be detected")

    total_memory = _total_memory_bytes()
    if total_memory is not None and total_memory < MIN_RECOMMENDED_MEMORY_BYTES:
        gb = total_memory / (1024 * 1024 * 1024)
        reasons.append(f"about {gb:.1f} GB RAM detected")

    free_storage = _free_storage_bytes()
    if (
        free_storage is not None
        and free_storage < MIN_RECOMMENDED_FREE_STORAGE_BYTES
    ):
        gb = free_storage / (1024 * 1024 * 1024)
        reasons.append(f"about {gb:.1f} GB free storage detected")

    if not _can_bind_localhost():
        reasons.append("could not bind a local TCP port")

    deps_installed = server_dependencies_installed()
    recommended = not reasons

    return NodeCapability(
        recommended=recommended,
        can_override=True,
        server_dependencies_installed=deps_installed,
        reasons=reasons,
    )


def server_dependencies_installed() -> bool:
    """Return whether optional server dependencies are importable."""

    return (
        importlib.util.find_spec("fastapi") is not None
        and importlib.util.find_spec("uvicorn") is not None
    )


def _is_mobile_environment() -> bool:
    """Detect mobile shells without importing platform-specific packages."""

    prefix = os.environ.get("PREFIX", "")
    termux_version = os.environ.get("TERMUX_VERSION")
    android_root = os.environ.get("ANDROID_ROOT")
    android_data = os.environ.get("ANDROID_DATA")
    platform_name = platform.platform().lower()
    return (
        bool(termux_version)
        or "com.termux" in prefix
        or bool(android_root)
        or bool(android_data)
        or "android" in platform_name
    )


def _total_memory_bytes() -> int | None:
    """Best-effort total memory detection."""

    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    if line.startswith("MemTotal:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return int(parts[1]) * 1024
        except OSError:
            return None

    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if isinstance(pages, int) and isinstance(page_size, int):
                return pages * page_size
        except (OSError, ValueError):
            return None

    # Windows memory detection is intentionally omitted to avoid extra
    # dependencies; unknown memory should not block node mode.
    if platform.system().lower() == "windows":
        return None

    return None


def _free_storage_bytes() -> int | None:
    """Return free space under the home directory."""

    try:
        return shutil.disk_usage(os.path.expanduser("~")).free
    except OSError:
        return None


def _can_bind_localhost() -> bool:
    """Return whether this process can bind a local node socket."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return True
    except OSError:
        return False
