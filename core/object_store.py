from core.index import ObjectIndex
from storage.objects import get_object, list_objects, save_object


class ObjectStore:
    def __init__(self):
        self.index = ObjectIndex()

    def put(self, obj: dict):
        if save_object(obj):
            self.index.index(obj)
        return obj["id"]

    def get(self, obj_id: str):
        return get_object(obj_id)

    def list_ids(self):
        return list_objects()
