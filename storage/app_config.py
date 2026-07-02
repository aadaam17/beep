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
    warnings: list[str]


CONFIG_ENV_VAR = "BEEP_CONFIG"
CONFIG_VERSION = 1
CONFIG_FILENAMES = (
    "beep.toml",
    "config.toml",
)
SUPPORTED_SECTIONS = {"version", "node", "network", "relay", "peers", "relays"}
SECTION_KEYS = {
    "node": {"enabled", "autostart", "prompted", "relay_only"},
    "network": {
        "relay_enabled",
        "strategy",
        "public_endpoint",
        "presence_ttl_seconds",
        "presence_refresh_seconds",
        "peer_auth_required",
        "peer_auth_token",
        "peer_auth_token_env",
    },
    "relay": {
        "max_object_bytes",
        "max_posts_per_minute",
        "max_objects_per_author",
        "max_objects_per_ip",
        "retention_limit",
        "relay_only",
        "denylisted_authors",
        "denylisted_ips",
    },
    "peers": {"urls"},
    "relays": {"urls"},
}

DEFAULT_CONFIG_TEXT = """# Beep configuration
version = 1

[node]
enabled = false
relay_only = false

[network]
relay_enabled = true
strategy = "prefer-direct"
public_endpoint = ""
presence_ttl_seconds = 86400
presence_refresh_seconds = 900
peer_auth_required = false
# Prefer peer_auth_token_env for shared secrets.
peer_auth_token_env = "BEEP_PEER_AUTH_TOKEN"

[relay]
max_object_bytes = 262144
max_posts_per_minute = 60
max_objects_per_author = 10000
max_objects_per_ip = 20000
retention_limit = 50000
relay_only = false
denylisted_authors = []
denylisted_ips = []

[peers]
urls = []

[relays]
urls = []
"""


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
        return {"path": None, "data": {}, "errors": [], "warnings": []}

    try:
        with path.open("rb") as handle:
            parsed = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        return {
            "path": str(path),
            "data": {},
            "errors": [f"TOML parse error: {exc}"],
            "warnings": [],
        }
    except OSError as exc:
        return {
            "path": str(path),
            "data": {},
            "errors": [f"Could not read config: {exc}"],
            "warnings": [],
        }

    if not isinstance(parsed, dict):
        return {
            "path": str(path),
            "data": {},
            "errors": ["Config must be a TOML table"],
            "warnings": [],
        }
    data = parsed
    errors, warnings = validate_app_config(data)
    return {"path": str(path), "data": data, "errors": errors, "warnings": warnings}


def validate_app_config(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Validate supported config sections and values."""

    errors: list[str] = []
    warnings: list[str] = []
    _validate_known_sections(data, warnings)
    _validate_version(data, errors)
    _validate_table(data, "node", errors)
    _validate_table(data, "network", errors)
    _validate_table(data, "relay", errors)
    _validate_endpoint_list(data, "peers", errors)
    _validate_endpoint_list(data, "relays", errors)
    _validate_known_keys(data, warnings)

    node = _table(data, "node")
    _expect_bool(node, "enabled", errors, "node.enabled")
    _expect_bool(node, "autostart", errors, "node.autostart")
    _expect_bool(node, "prompted", errors, "node.prompted")
    _expect_bool(node, "relay_only", errors, "node.relay_only")

    network = _table(data, "network")
    _expect_bool(network, "relay_enabled", errors, "network.relay_enabled")
    _expect_bool(network, "peer_auth_required", errors, "network.peer_auth_required")
    _expect_string(network, "peer_auth_token", errors, "network.peer_auth_token")
    _expect_string(network, "peer_auth_token_env", errors, "network.peer_auth_token_env")
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

    return errors, warnings


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
    token = _secret_from_env(network.get("peer_auth_token_env"))
    if token is None:
        _copy_string(network, overrides, "peer_auth_token", "peer_auth_token")
    else:
        overrides["peer_auth_token"] = token

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


def write_default_config(path: Path | None = None) -> Path:
    """Create a default config file without overwriting an existing file."""

    target = path or Path.cwd() / "beep.toml"
    target = target.expanduser()
    if target.exists():
        raise FileExistsError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
    return target


def effective_config_summary(*, redact_secrets: bool = True) -> dict[str, object]:
    """Return a concise, operator-friendly summary of active config settings."""

    result = load_app_config()
    overrides = network_policy_overrides()
    if redact_secrets and "peer_auth_token" in overrides:
        overrides["peer_auth_token"] = "***"
    return {
        "path": result["path"],
        "valid": not result["errors"],
        "errors": result["errors"],
        "warnings": result["warnings"],
        "network_policy_overrides": overrides,
        "peers": configured_peers(),
        "relays": configured_relays(),
    }


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


def _validate_known_sections(data: dict[str, Any], warnings: list[str]) -> None:
    for section in sorted(data):
        if section not in SUPPORTED_SECTIONS:
            warnings.append(f"unknown section ignored: {section}")


def _validate_known_keys(data: dict[str, Any], warnings: list[str]) -> None:
    for section, allowed_keys in SECTION_KEYS.items():
        value = data.get(section)
        if not isinstance(value, dict):
            continue
        for key in sorted(value):
            if key not in allowed_keys:
                warnings.append(f"unknown key ignored: {section}.{key}")


def _validate_version(data: dict[str, Any], errors: list[str]) -> None:
    version = data.get("version")
    if version is None:
        return
    if not isinstance(version, int) or isinstance(version, bool):
        errors.append("version must be an integer")
        return
    if version != CONFIG_VERSION:
        errors.append(f"unsupported config version: {version}")


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


def _secret_from_env(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    token = os.getenv(value)
    return token if token is not None else None


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
