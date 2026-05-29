# storage/rooms.py
"""Room record storage and retrieval."""

from .fs import BeepFS

fs = BeepFS()


def list_rooms():
    return fs.list_rooms()


def read_room(name):
    room = fs._read_room(name)
    if not room:
        return []
    return room.get("messages", [])
