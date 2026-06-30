"""Optional TOML configuration file support for Beep."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, TypedDict


class ConfigResult(TypedDict):
    """Loaded app configuration with diagnostics."""

    path: str | None
    data: dict[str, Any]
    errors: list[str]


CONFIG_ENV_VAR = "BEEP_CONFIG"
CONFIG_FILENAMES = (
    "beep.toml",
    "config.toml",
)


def config_search_paths() -> list[Path]:
    """Return config locations in precedence order."""

    paths: list[Path] = []
    env_path = os.getenv(CONFIG_ENV_VAR)
    if env_path:
        paths.append(Path(env_path).expanduser())

    cwd = Path.cwd()
    paths.extend(cwd / filename for filename in CONFIG_FILENAMES)
    paths.append(Path.home() / ".config" / "beep" / "config.toml")
    paths.append(Path.home() / ".beep" / "config.toml")
    return _dedupe_paths(paths)


def find_config_path() -> Path | None:
    """Return the first existing config file, if any."""

    for path in config_search_paths():
        if path.exists() and path.is_file():
            return path
    return None


def load_app_config() -> ConfigResult:
    """Load the optional TOML config file."""

    path = find_config_path()
    if path is None:
        return {"path": None, "data": {}, "errors": []}

    try:
        with path.open("rb") as handle:
            parsed = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        return {"path": str(path), "data": {}, "errors": [f"TOML parse error: {exc}"]}
    except OSError as exc:
        return {"path": str(path), "data": {}, "errors": [f"Could not read config: {exc}"]}

    if not isinstance(parsed, dict):
        return {"path": str(path), "data": {}, "errors": ["Config must be a TOML table"]}
    data = parsed
    errors = validate_app_config(data)
    return {"path": str(path), "data": data, "errors": errors}


def validate_app_config(data: dict[str, Any]) -> list[str]:
    """Validate supported config sections and values."""

    errors: list[str] = []
    _validate_table(data, "node", errors)
    _validate_table(data, "network", errors)
    _validate_table(data, "relay", errors)
    _validate_endpoint_list(data, "peers", errors)
    _validate_endpoint_list(data, "relays", errors)

    node = _table(data, "node")
    _expect_bool(node, "enabled", errors, "node.enabled")
    _expect_bool(node, "autostart", errors, "node.autostart")
    _expect_bool(node, "prompted", errors, "node.prompted")
    _expect_bool(node, "relay_only", errors, "node.relay_only")

    network = _table(data, "network")
    _expect_bool(network, "relay_enabled", errors, "network.relay_enabled")
    _expect_bool(network, "peer_auth_required", errors, "network.peer_auth_required")
    _expect_string(network, "peer_auth_token", errors, "network.peer_auth_token")
    _expect_string(network, "public_endpoint", errors, "network.public_endpoint")
    _expect_strategy(network, "strategy", errors, "network.strategy")
    _expect_positive_int(
        network,
        "presence_ttl_seconds",
        errors,
        "network.presence_ttl_seconds",
    )
    _expect_positive_int(
        network,
        "presence_refresh_seconds",
        errors,
        "network.presence_refresh_seconds",
    )

    relay = _table(data, "relay")
    _expect_positive_int(relay, "max_object_bytes", errors, "relay.max_object_bytes")
    _expect_positive_int(relay, "max_posts_per_minute", errors, "relay.max_posts_per_minute")
    _expect_positive_int(
        relay,
        "max_objects_per_author",
        errors,
        "relay.max_objects_per_author",
    )
    _expect_positive_int(
        relay,
        "max_objects_per_ip",
        errors,
        "relay.max_objects_per_ip",
    )
    _expect_positive_int(relay, "retention_limit", errors, "relay.retention_limit")
    _expect_bool(relay, "relay_only", errors, "relay.relay_only")
    _expect_string_list(relay, "denylisted_authors", errors, "relay.denylisted_authors")
    _expect_string_list(relay, "denylisted_ips", errors, "relay.denylisted_ips")

    return errors


def network_policy_overrides() -> dict[str, object]:
    """Return validated network policy overrides from the config file."""

    result = load_app_config()
    if result["errors"]:
        return {}
    data = result["data"]
    overrides: dict[str, object] = {}

    node = _table(data, "node")
    _copy_bool(node, overrides, "enabled", "node_autostart")
    _copy_bool(node, overrides, "autostart", "node_autostart")
    _copy_bool(node, overrides, "prompted", "node_prompted")
    _copy_bool(node, overrides, "relay_only", "relay_only_mode")

    network = _table(data, "network")
    _copy_bool(network, overrides, "relay_enabled", "relay_enabled")
    _copy_string(network, overrides, "strategy", "strategy")
    _copy_string(network, overrides, "public_endpoint", "public_endpoint")
    _copy_int(network, overrides, "presence_ttl_seconds", "presence_ttl_seconds")
    _copy_int(network, overrides, "presence_refresh_seconds", "presence_refresh_seconds")
    _copy_bool(network, overrides, "peer_auth_required", "peer_auth_required")
    _copy_string(network, overrides, "peer_auth_token", "peer_auth_token")

    relay = _table(data, "relay")
    _copy_int(relay, overrides, "max_object_bytes", "max_object_bytes")
    _copy_int(relay, overrides, "max_posts_per_minute", "max_posts_per_minute")
    _copy_int(relay, overrides, "max_objects_per_author", "max_objects_per_author")
    _copy_int(relay, overrides, "max_objects_per_ip", "max_objects_per_ip")
    _copy_int(relay, overrides, "retention_limit", "relay_retention_limit")
    _copy_bool(relay, overrides, "relay_only", "relay_only_mode")
    _copy_string_list(relay, overrides, "denylisted_authors", "denylisted_authors")
    _copy_string_list(relay, overrides, "denylisted_ips", "denylisted_ips")
    return overrides


def configured_peers() -> list[str]:
    """Return peer URLs declared in config."""

    return _configured_endpoint_list("peers")


def configured_relays() -> list[str]:
    """Return relay URLs declared in config."""

    return _configured_endpoint_list("relays")


def _configured_endpoint_list(section: str) -> list[str]:
    result = load_app_config()
    if result["errors"]:
        return []
    value = result["data"].get(section)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        urls = value.get("urls")
        if isinstance(urls, list):
            return [item for item in urls if isinstance(item, str)]
    return []


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _validate_table(data: dict[str, Any], key: str, errors: list[str]) -> None:
    if key in data and not isinstance(data[key], dict):
        errors.append(f"{key} must be a table")


def _validate_endpoint_list(data: dict[str, Any], key: str, errors: list[str]) -> None:
    if key not in data:
        return
    value = data[key]
    if isinstance(value, list):
        if any(not isinstance(item, str) for item in value):
            errors.append(f"{key} must contain only strings")
        return
    if isinstance(value, dict):
        urls = value.get("urls")
        if urls is not None and (
            not isinstance(urls, list) or any(not isinstance(item, str) for item in urls)
        ):
            errors.append(f"{key}.urls must contain only strings")
        return
    errors.append(f"{key} must be a list or table")


def _expect_bool(data: dict[str, Any], key: str, errors: list[str], label: str) -> None:
    if key in data and not isinstance(data[key], bool):
        errors.append(f"{label} must be bool")


def _expect_string(data: dict[str, Any], key: str, errors: list[str], label: str) -> None:
    if key in data and not isinstance(data[key], str):
        errors.append(f"{label} must be string")


def _expect_positive_int(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    label: str,
) -> None:
    if key in data and (
        not isinstance(data[key], int)
        or isinstance(data[key], bool)
        or data[key] <= 0
    ):
        errors.append(f"{label} must be a positive integer")


def _expect_string_list(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    label: str,
) -> None:
    if key in data and (
        not isinstance(data[key], list)
        or any(not isinstance(item, str) for item in data[key])
    ):
        errors.append(f"{label} must contain only strings")


def _expect_strategy(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    label: str,
) -> None:
    if key in data and data[key] not in {"prefer-direct", "direct-only", "relay-first"}:
        errors.append(f"{label} must be prefer-direct, direct-only, or relay-first")


def _copy_bool(
    source: dict[str, Any],
    target: dict[str, object],
    source_key: str,
    target_key: str,
) -> None:
    value = source.get(source_key)
    if isinstance(value, bool):
        target[target_key] = value


def _copy_string(
    source: dict[str, Any],
    target: dict[str, object],
    source_key: str,
    target_key: str,
) -> None:
    value = source.get(source_key)
    if isinstance(value, str):
        target[target_key] = value


def _copy_int(
    source: dict[str, Any],
    target: dict[str, object],
    source_key: str,
    target_key: str,
) -> None:
    value = source.get(source_key)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        target[target_key] = value


def _copy_string_list(
    source: dict[str, Any],
    target: dict[str, object],
    source_key: str,
    target_key: str,
) -> None:
    value = source.get(source_key)
    if isinstance(value, list):
        target[target_key] = [item for item in value if isinstance(item, str)]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
