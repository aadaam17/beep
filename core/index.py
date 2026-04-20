from collections import defaultdict

from storage.objects import query_objects


class ObjectIndex:
    def __init__(self):
        self.objects = {}
        self.by_author = defaultdict(set)
        self.by_type = defaultdict(set)
        self.by_time = []
        self._rebuild()

    def _rebuild(self):
        for obj in query_objects():
            self.index(obj)

    def index(self, obj: dict):
        obj_id = obj["id"]

        if obj_id in self.objects:
            return

        self.objects[obj_id] = obj
        self.by_author[obj["author"]].add(obj_id)
        self.by_type[obj["type"]].add(obj_id)
        self.by_time.append((obj["timestamp"], obj_id))

    def get_by_author(self, author):
        return list(self.by_author.get(author, set()))

    def get_by_type(self, type_):
        return list(self.by_type.get(type_, set()))

    def get_recent(self, limit=50):
        sorted_items = sorted(self.by_time, reverse=True)
        return [obj_id for _, obj_id in sorted_items[:limit]]

    def get(self, obj_id: str):
        return self.objects.get(obj_id)

    def get_all(self):
        return list(self.objects.values())
