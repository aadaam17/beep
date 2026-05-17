"""Compatibility wrapper around the canonical object storage layer."""

from __future__ import annotations

from typing import cast

from core.index import ObjectIndex
from core.types import BeepObjectRecord, ObjectSerializable
from storage.objects import get_object, list_objects, save_object


class ObjectStore:
    """Legacy object-store facade backed by the canonical storage module."""

    def __init__(self) -> None:
        self.index = ObjectIndex()

    def put(self, obj: ObjectSerializable | BeepObjectRecord) -> str:
        """Store an object and update the in-memory index when accepted."""

        if hasattr(obj, "to_dict"):
            object_record = cast(ObjectSerializable, obj).to_dict()
        else:
            object_record = obj
        if save_object(object_record, auto_push=False):
            self.index.index(object_record)
        return object_record["id"]

    def get(self, obj_id: str) -> BeepObjectRecord | None:
        """Load an object by ID."""

        return get_object(obj_id)

    def list_ids(self) -> list[str]:
        """List all stored object IDs."""

        return list_objects()
