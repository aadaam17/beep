# core/index.py
"""In-memory index of Beep objects for fast retrieval and querying."""

from collections import defaultdict
from typing import DefaultDict

from core.types import BeepObjectRecord
from storage.objects import query_objects


class ObjectIndex:
    def __init__(self) -> None:
        self.objects: dict[str, BeepObjectRecord] = {}
        self.by_author: DefaultDict[str, set[str]] = defaultdict(set)
        self.by_type: DefaultDict[str, set[str]] = defaultdict(set)
        self.by_time: list[tuple[float, str]] = []
        self._rebuild()

    def _rebuild(self) -> None:
        for obj in query_objects():
            self.index(obj)

    def index(self, obj: BeepObjectRecord) -> None:
        obj_id = obj["id"]

        if obj_id in self.objects:
            return

        self.objects[obj_id] = obj
        self.by_author[obj["author"]].add(obj_id)
        self.by_type[obj["type"]].add(obj_id)
        self.by_time.append((obj["timestamp"], obj_id))

    def get_by_author(self, author: str) -> list[str]:
        return list(self.by_author.get(author, set()))

    def get_by_type(self, type_: str) -> list[str]:
        return list(self.by_type.get(type_, set()))

    def get_recent(self, limit: int = 50) -> list[str]:
        sorted_items = sorted(self.by_time, reverse=True)
        return [obj_id for _, obj_id in sorted_items[:limit]]

    def get(self, obj_id: str) -> BeepObjectRecord | None:
        return self.objects.get(obj_id)

    def get_all(self) -> list[BeepObjectRecord]:
        return list(self.objects.values())
    