"""Private Meaning Layer cipher profile storage and transforms."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

from storage.atomic import atomic_write_json, read_json_with_backup

CIPHER_DIR = Path.home() / ".beep" / "ciphers"
CIPHER_EXPORT_VERSION = 1


class CipherProfile(TypedDict):
    """Local PML cipher profile."""

    profile: str
    version: int
    status: str
    fingerprint: str
    mapping: dict[str, str]


def create_profile(profile: str) -> CipherProfile:
    """Create an empty cipher profile."""

    profile = _validate_profile_name(profile)
    path = _profile_path(profile, 1)
    if path.exists():
        raise FileExistsError(f"cipher profile already exists: {profile}")
    data = _profile_record(profile, 1, {}, status="active")
    _save_profile(data)
    return data


def list_profiles() -> list[CipherProfile]:
    """List all local cipher profiles."""

    CIPHER_DIR.mkdir(parents=True, exist_ok=True)
    profiles: list[CipherProfile] = []
    for path in sorted(CIPHER_DIR.glob("*.json")):
        profile = _load_profile_path(path)
        if profile is not None:
            profiles.append(profile)
    return sorted(profiles, key=lambda item: (item["profile"], item["version"]))


def load_profile(profile: str, version: int | None = None) -> CipherProfile:
    """Load a cipher profile by name and optional version."""

    profile = _validate_profile_name(profile)
    if version is not None:
        loaded = _load_profile_path(_profile_path(profile, version))
        if loaded is None:
            raise FileNotFoundError(f"cipher profile not found: {profile} v{version}")
        return loaded

    matches = [item for item in list_profiles() if item["profile"] == profile]
    if not matches:
        raise FileNotFoundError(f"cipher profile not found: {profile}")
    return max(matches, key=lambda item: item["version"])


def set_mapping(profile: str, phrase: str, code: str) -> CipherProfile:
    """Set a phrase-to-code mapping."""

    if not phrase or not code:
        raise ValueError("phrase and code are required")
    data = load_profile(profile)
    _ensure_active(data)
    data["mapping"][phrase] = code
    data["fingerprint"] = fingerprint_mapping(data["profile"], data["version"], data["mapping"])
    _save_profile(data)
    return data


def unset_mapping(profile: str, phrase: str) -> CipherProfile:
    """Remove a phrase mapping."""

    data = load_profile(profile)
    _ensure_active(data)
    data["mapping"].pop(phrase, None)
    data["fingerprint"] = fingerprint_mapping(data["profile"], data["version"], data["mapping"])
    _save_profile(data)
    return data


def encode_text(text: str, profile: str) -> tuple[str, CipherProfile]:
    """Encode text with a local cipher profile."""

    data = load_profile(profile)
    _ensure_active(data)
    encoded = _replace_tokens(text, data["mapping"])
    return encoded, data


def decode_text(text: str, profile: str, version: int | None = None) -> tuple[str, bool]:
    """Decode text with a local cipher profile."""

    try:
        data = load_profile(profile, version)
    except FileNotFoundError:
        return text, False
    reverse = {code: phrase for phrase, code in data["mapping"].items()}
    return _replace_tokens(text, reverse), True


def export_profile(profile: str, output: Path | None = None) -> Path:
    """Export a profile to a portable .beepcipher file."""

    data = load_profile(profile)
    export = {
        "profile": data["profile"],
        "version": data["version"],
        "fingerprint": data["fingerprint"],
        "mapping": data["mapping"],
    }
    target = output or Path.cwd() / f"{data['profile']}.beepcipher"
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(export, indent=2, sort_keys=True), encoding="utf-8")
    return target


def import_profile(
    path: Path,
    *,
    as_profile: str | None = None,
    replace: bool = False,
    merge: bool = False,
) -> CipherProfile:
    """Import a portable .beepcipher profile into the local store."""

    raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("cipher export must be an object")
    profile = _validate_profile_name(str(as_profile or raw.get("profile") or ""))
    version = raw.get("version")
    mapping = raw.get("mapping")
    fingerprint = raw.get("fingerprint")
    if not isinstance(version, int) or version <= 0:
        raise ValueError("cipher version must be a positive integer")
    if not isinstance(mapping, dict):
        raise ValueError("cipher mapping must be an object")
    clean_mapping = {
        str(phrase): str(code)
        for phrase, code in mapping.items()
        if isinstance(phrase, str) and phrase and isinstance(code, str) and code
    }
    expected = fingerprint_mapping(str(raw.get("profile") or profile), version, clean_mapping)
    if fingerprint != expected:
        raise ValueError("cipher fingerprint mismatch")

    target = _profile_path(profile, version)
    if target.exists() and not replace and not merge:
        raise FileExistsError(f"cipher profile already exists: {profile} v{version}")

    if merge and target.exists():
        existing = load_profile(profile, version)
        clean_mapping = {**existing["mapping"], **clean_mapping}

    data = _profile_record(profile, version, clean_mapping, status="active")
    _save_profile(data)
    return data


def rotate_profile(profile: str) -> CipherProfile:
    """Create the next version of a profile with copied mappings."""

    current = load_profile(profile)
    next_version = current["version"] + 1
    data = _profile_record(
        current["profile"],
        next_version,
        dict(current["mapping"]),
        status="active",
    )
    _save_profile(data)
    return data


def revoke_profile(profile: str, version: int | None = None) -> CipherProfile:
    """Mark a cipher profile unsafe for future sends."""

    data = load_profile(profile, version)
    data["status"] = "revoked"
    _save_profile(data)
    return data


def fingerprint_mapping(profile: str, version: int, mapping: dict[str, str]) -> str:
    """Return a stable fingerprint for a profile mapping."""

    payload = {
        "profile": profile,
        "version": version,
        "mapping": dict(sorted(mapping.items())),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    import hashlib

    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _profile_record(
    profile: str,
    version: int,
    mapping: dict[str, str],
    *,
    status: str,
) -> CipherProfile:
    return {
        "profile": profile,
        "version": version,
        "status": status,
        "fingerprint": fingerprint_mapping(profile, version, mapping),
        "mapping": dict(sorted(mapping.items())),
    }


def _save_profile(data: CipherProfile) -> None:
    CIPHER_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_profile_path(data["profile"], data["version"]), data, indent=2)


def _load_profile_path(path: Path) -> CipherProfile | None:
    raw = read_json_with_backup(path)
    if not isinstance(raw, dict):
        return None
    profile = raw.get("profile")
    version = raw.get("version")
    mapping = raw.get("mapping")
    status = raw.get("status", "active")
    if not isinstance(profile, str) or not isinstance(version, int):
        return None
    if not isinstance(mapping, dict):
        return None
    clean_mapping = {
        phrase: code
        for phrase, code in mapping.items()
        if isinstance(phrase, str) and phrase and isinstance(code, str) and code
    }
    fingerprint = raw.get("fingerprint")
    expected = fingerprint_mapping(profile, version, clean_mapping)
    if isinstance(fingerprint, str) and fingerprint != expected:
        return None
    return _profile_record(
        _validate_profile_name(profile),
        version,
        clean_mapping,
        status=status if status in {"active", "revoked"} else "active",
    )


def _profile_path(profile: str, version: int) -> Path:
    if version == 1:
        return CIPHER_DIR / f"{profile}.json"
    return CIPHER_DIR / f"{profile}.v{version}.json"


def _validate_profile_name(profile: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", profile):
        raise ValueError("profile must use letters, numbers, dots, dashes, or underscores")
    return profile


def _ensure_active(data: CipherProfile) -> None:
    if data["status"] != "active":
        raise PermissionError(f"cipher profile is revoked: {data['profile']} v{data['version']}")


def _replace_tokens(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    keys = sorted(mapping, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(key) for key in keys))
    return pattern.sub(lambda match: mapping[match.group(0)], text)
