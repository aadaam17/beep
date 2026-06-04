# storage/fs.py
""" File system based storage for Beep """

from pathlib import Path
from typing import cast

from core.object import BeepObject
from storage.atomic import atomic_write_json
from storage.objects import get_object, query_objects, save_object
from storage.profile import get_user_by_pubkey, update_user
from storage.chat_service import ChatService
from storage.room_service import RoomService

from core.types import ChatMessage, ChatRecord, PostView, RoomMessage, RoomState

STORAGE_DIR = Path.home() / ".beep" / "beep_storage"
POSTS_DIR = STORAGE_DIR / "posts"
ROOMS_DIR = STORAGE_DIR / "rooms"
USER_DIR = STORAGE_DIR / "users"
CHATS_DIR = STORAGE_DIR / "chats"

for path in (STORAGE_DIR, POSTS_DIR, ROOMS_DIR, USER_DIR, CHATS_DIR):
    path.mkdir(exist_ok=True)


class BeepFS:
    def __init__(self) -> None:
        self.chat = ChatService()
        self.rooms = RoomService()

    @staticmethod
    def _read_json(path: Path, default: object = None) -> object:
        from storage.atomic import read_json_with_backup

        return read_json_with_backup(path, default=default)

    @staticmethod
    def _write_json(path: Path, data: object) -> None:
        atomic_write_json(path, data, indent=4)

    def user_exists(self, username: str) -> bool:
        """Check whether a local user record exists for the given username."""
        from storage.profile import get_user
        return get_user(username) is not None

    def list_posts(self, only_existing_users: bool = False) -> list[str]:
        posts = query_objects(obj_type="post")

        if not only_existing_users:
            return [obj["id"] for obj in posts if obj.get("id")]

        return [obj["id"] for obj in posts if obj.get("id") and get_user_by_pubkey(obj["author"])]

    def list_followed_posts(self, username: str) -> list[str]:
        from storage.profile import get_user

        user = get_user(username)
        if not user:
            return []

        followed = set(user.get("following", []))
        return [
            post_id
            for post_id in self.list_posts(only_existing_users=True)
            if self.read_post(post_id).get("creator") in followed
        ]

    def post_path(self, post_id: str) -> Path:
        return POSTS_DIR / f"{post_id}.json"

    def read_post(self, post_id: str) -> PostView:
        obj = get_object(post_id)
        if not obj:
            return {
                "creator": None,
                "content": "[missing]",
                "revoked": True,
                "shared_from": None,
                "type": None,
            }

        shared_from = obj.get("meta", {}).get("shared_from")
        parent_id = obj.get("meta", {}).get("parent_id")
        quote = obj.get("meta", {}).get("quote", False)
        return {
            "creator": obj["author"],
            "content": obj["content"],
            "timestamp": obj["timestamp"],
            "type": obj["type"],
            "revoked": False,
            "shared_from": shared_from if isinstance(shared_from, str) else None,
            "parent_id": parent_id if isinstance(parent_id, str) else None,
            "quote": bool(quote),
        }

    def save_post(self, post_id: str, data: PostView) -> None:
        self._write_json(self.post_path(post_id), data)

    def create_post(
        self,
        creator: str,
        content: str,
        shared_from: str | None = None,
        quote: bool = False,
        post_type: str = "post",
        parent_id: str | None = None,
    ) -> str | None:
        obj = BeepObject.create_object(
            type_=post_type,
            author_pubkey=creator,
            content=content,
            meta={"shared_from": shared_from, "quote": quote, "parent_id": parent_id},
        )

        save_object(obj.to_dict())

        user = get_user_by_pubkey(creator)
        if user:
            target = "shared" if post_type in {"share", "quote"} else "posts"
            post_object_id = obj.id
            if post_object_id is not None:
                user.setdefault(target, []).append(post_object_id)
            if user["username"] in self._local_usernames():
                update_user(user["username"], user)

        return obj.id

    def delete_post(self, post_id: str, username: str) -> None:
        post = self.read_post(post_id)
        if post.get("creator") != username:
            raise PermissionError("Cannot delete another user's post")
        post["revoked"] = True
        self.save_post(post_id, post)

    def _local_usernames(self) -> set[str]:
        user_file = Path.home() / ".beep" / "beep_users.json"
        raw_data = self._read_json(user_file, default={})
        if not isinstance(raw_data, dict):
            return set()
        user_map = cast(dict[str, object], raw_data)
        return set(user_map.keys())

    def list_rooms(self) -> list[str]:
        return self.rooms.list_rooms()

    def _read_room(self, name: str) -> RoomState | None:
        return self.rooms.build_room_state(name)

    def create_room(
        self,
        name: str,
        creator: str,
        private: bool = False,
        ttl: float | None = None,
    ) -> None:
        return self.rooms.create_room(name, creator, private=private, ttl=ttl)

    def join_room(self, name: str, user: str, re_encrypt_old: bool = False) -> str:
        return self.rooms.join_room(name, user, re_encrypt_old=re_encrypt_old)

    def leave_room(self, name: str, user: str) -> str:
        return self.rooms.leave_room(name, user)

    def dissolve_room(self, name: str, user: str) -> str:
        return self.rooms.dissolve_room(name, user)

    def invite(self, room_name: str, user: str, actor: str | None = None) -> str:
        return self.rooms.invite(room_name, user, actor=actor)

    def say(self, room_name: str, sender: str, message: str) -> None:
        return self.rooms.say(room_name, sender, message)

    def read_messages(
        self,
        room_name: str,
        username: str,
        start: int = 0,
        limit: int = 10,
    ) -> tuple[list[RoomMessage], int]:
        return self.rooms.read_messages(room_name, username, start=start, limit=limit)

    def room_mod(self, room_name: str, actor: str, target: str, promote: bool = True) -> str:
        return self.rooms.room_mod(room_name, actor, target, promote=promote)

    def room_mute(
        self,
        room_name: str,
        actor: str,
        target: str,
        permanent: bool = False,
    ) -> str:
        return self.rooms.room_mute(room_name, actor, target, permanent=permanent)

    def room_unmute(self, room_name: str, actor: str, target: str) -> str:
        return self.rooms.room_unmute(room_name, actor, target)

    def room_kick(self, room_name: str, actor: str, target: str) -> str:
        return self.rooms.room_kick(room_name, actor, target)

    def list_chats(self, username: str | None = None) -> list[str]:
        return self.chat.list_chats(username=username)

    def create_chat(self, chat_name: str | None, user_a: str, user_b: str) -> str:
        return self.chat.create_chat(chat_name, user_a, user_b)

    def read_chat(self, name: str) -> ChatRecord:
        return self.chat.read_chat(name)

    def chat_say(self, chat_peer: str, sender: str, message: str) -> None:
        return self.chat.chat_say(chat_peer, sender, message)

    def chat_read_messages(
        self,
        chat_peer: str,
        user: str,
        start: int = 0,
        limit: int = 10,
    ) -> tuple[list[ChatMessage], int]:
        return self.chat.chat_read_messages(chat_peer, user, start=start, limit=limit)
