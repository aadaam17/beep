# core/schemas.py
"""Validation logic for versioned Beep object schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from collections.abc import Mapping

SCHEMA_FILE = (
    Path(__file__).parent
    / "protocol_schemas"
    / "v1"
    / "object-types.schema.json"
)


@lru_cache(maxsize=1)
def load_object_type_schemas() -> dict[str, Any]:
    """Load the checked-in protocol schema document."""

    with SCHEMA_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("object schema document must be a JSON object")
    return data


def validate_object_schema(obj: Mapping[str, Any]) -> list[str]:
    """Validate an object against the versioned external schema document."""

    errors: list[str] = []
    obj_type = obj.get("type")
    meta = obj.get("meta", {})

    if not isinstance(meta, dict):
        return ["meta must be an object"]
    if not isinstance(obj_type, str):
        return ["type must be str"]

    schema_doc = load_object_type_schemas()
    object_types = schema_doc.get("object_types", {})
    if not isinstance(object_types, dict):
        raise ValueError("object schema document is missing object_types")

    type_schema = object_types.get(obj_type)
    if not isinstance(type_schema, dict):
        return errors

    meta_schema = type_schema.get("meta", {})
    if isinstance(meta_schema, dict):
        _validate_schema(meta, meta_schema, schema_doc, errors, prefix="meta")

    return errors


def _validate_schema(
    value: Any,
    schema: dict[str, Any],
    schema_doc: dict[str, Any],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    schema = _resolve_schema(schema, schema_doc)
    if schema.get("type") == "object" and not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return
    if not isinstance(value, dict):
        return

    required = schema.get("required", [])
    if isinstance(required, list):
        _require_keys(value, {key for key in required if isinstance(key, str)}, errors, prefix=prefix)

    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for key, property_schema in properties.items():
            if not isinstance(key, str) or key not in value:
                continue
            if isinstance(property_schema, dict):
                _validate_property(
                    value[key],
                    property_schema,
                    schema_doc,
                    errors,
                    prefix=f"{prefix}.{key}",
                )

    any_required = schema.get("anyRequired", [])
    if isinstance(any_required, list):
        _validate_any_required(value, any_required, errors, prefix=prefix)

    conditional_required = schema.get("conditionalRequired", {})
    if isinstance(conditional_required, dict):
        _validate_conditional_required(
            value,
            conditional_required,
            errors,
            prefix=prefix,
        )


def _validate_property(
    value: Any,
    schema: dict[str, Any],
    schema_doc: dict[str, Any],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    schema = _resolve_schema(schema, schema_doc)

    if "const" in schema:
        expected = schema["const"]
        if value != expected:
            errors.append(f"{prefix} must be {expected}")
        return

    if "enum" in schema:
        options = schema["enum"]
        if isinstance(options, list) and value not in options:
            errors.append(f"{prefix} must be one of: {', '.join(str(item) for item in options)}")
        return

    expected_type = schema.get("type")
    if expected_type is not None and not _matches_json_type(value, expected_type):
        errors.append(f"{prefix} must be {_type_label(expected_type)}")
        return

    if isinstance(schema.get("properties"), dict) or isinstance(schema.get("required"), list):
        _validate_schema(value, schema, schema_doc, errors, prefix=prefix)


def _resolve_schema(schema: dict[str, Any], schema_doc: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    prefix = "#/definitions/"
    if not ref.startswith(prefix):
        return schema
    definitions = schema_doc.get("definitions", {})
    if not isinstance(definitions, dict):
        return schema
    resolved = definitions.get(ref.removeprefix(prefix))
    return resolved if isinstance(resolved, dict) else schema


def _validate_any_required(
    data: dict[str, Any],
    groups: list[Any],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    normalized = [
        [item for item in group if isinstance(item, str)]
        for group in groups
        if isinstance(group, list)
    ]
    if any(any(key in data for key in group) for group in normalized):
        return

    flattened = {key for group in normalized for key in group}
    if {"enc_pubkey", "enc_fingerprint", "rsa_pubkey", "rsa_fingerprint"}.issubset(flattened):
        errors.append(
            "meta.enc_pubkey/meta.enc_fingerprint or meta.rsa_pubkey/meta.rsa_fingerprint is required"
        )
        return
    if {"encrypted", "recovery_encrypted"}.issubset(flattened):
        errors.append("meta.encrypted or meta.recovery_encrypted is required")


def _validate_conditional_required(
    data: dict[str, Any],
    rules: dict[str, Any],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    for field, cases in rules.items():
        if not isinstance(field, str) or not isinstance(cases, dict):
            continue
        selector = data.get(field)
        required = cases.get(selector)
        if isinstance(required, list):
            _require_keys(
                data,
                {key for key in required if isinstance(key, str)},
                errors,
                prefix=prefix,
            )


def _require_keys(
    data: dict[str, Any], keys: set[str], errors: list[str], *, prefix: str
) -> None:
    missing = sorted(keys.difference(data))
    for key in missing:
        errors.append(f"{prefix}.{key} is required")


def _matches_json_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_json_type(value, item) for item in expected)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True


def _type_label(expected: Any) -> str:
    if expected == "integer":
        return "int"
    if expected == "boolean":
        return "bool"
    if isinstance(expected, list):
        labels = [_type_label(item) for item in expected]
        return " or ".join(labels)
    if isinstance(expected, str):
        return expected
    return str(expected)
