import time
import json
from pathlib import Path

from core.object import BeepObject
from storage.objects import save_object, get_object, query_objects

from storage.crypto import load_or_create_keys
from storage.profile import get_user, get_user_by_pubkey, update_user

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes


# ---------------- PATHS ----------------

STORAGE_DIR = Path.home() / ".beep_storage"
POSTS_DIR = STORAGE_DIR / "posts"
ROOMS_DIR = STORAGE_DIR / "rooms"
USER_DIR = STORAGE_DIR / "users"  # crypto keys only
CHATS_DIR = STORAGE_DIR / "chats"

for path in (STORAGE_DIR, POSTS_DIR, ROOMS_DIR, USER_DIR, CHATS_DIR):
    path.mkdir(exist_ok=True)

PAGE = 10

# ================= FILESYSTEM =================


class BeepFS:
    # ------------ GENERIC HELPERS ------------
    @staticmethod
    def _read_json(path, default=None):
        if not path.exists():
            return default
        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=4)

    # ---------------- POSTS ----------------
    # def list_posts(self, only_existing_users=True):
    #     posts = sorted((p.stem for p in POSTS_DIR.glob("*.json")), reverse=True)
    #     if only_existing_users:
    #         valid_posts = []
    #         for pid in posts:
    #             post = self.read_post(pid)
    #             creator = post.get("creator")
    #             if creator and get_user(creator):
    #                 valid_posts.append(pid)
    #         return valid_posts
    #     return posts

    def list_posts(self, only_existing_users: bool = False):
        posts = query_objects(obj_type="post")

        if not only_existing_users:
            return [o["id"] for o in posts]

        return [
            o["id"]
            for o in posts
            if get_user_by_pubkey(o["author"])
        ]

    def list_followed_posts(self, username):
        user = get_user(username)
        if not user:
            return []
        followed = set(user.get("following", []))
        posts = self.list_posts(only_existing_users=True)
        return [
            post_id
            for post_id in posts
            if self.read_post(post_id).get("creator") in followed
        ]

    def post_path(self, post_id):
        return POSTS_DIR / f"{post_id}.json"

    # def read_post(self, post_id):
    #     return self._read_json(
    #         self.post_path(post_id),
    #         default={
    #             "creator": None,
    #             "content": "[missing]",
    #             "revoked": True,
    #             "shared_from": None,
    #         },
    #     )

    def read_post(self, post_id):
        obj = get_object(post_id)
        if not obj:
            return {
                "creator": None,
                "content": "[missing]",
                "revoked": True,
                "shared_from": None,
                "type": None
            }

        return {
            "creator": obj["author"],
            "content": obj["content"],
            "timestamp": obj["timestamp"],
            "type": obj["type"],
            "revoked": False,
            "shared_from": obj.get("meta", {}).get("shared_from"),
            "parent_id": obj.get("meta", {}).get("parent_id"),
            "quote": obj.get("meta", {}).get("quote", False)
        }

    def save_post(self, post_id, data):
        self._write_json(self.post_path(post_id), data)

    # ---------------- UPDATED CREATE_POST ----------------
    # def create_post(self, creator, content, shared_from=None, quote=False, post_type="post", parent_id=None):
    #     """
    #     Create a new post.
    #     - creator: username
    #     - content: text content of the post
    #     - shared_from: post_id if this is a shared/quoted post
    #     - quote: True if this is a quoted post
    #     - post_type: "post", "comment", "share", "quote"
    #     - parent_id: parent post id for comments
    #     """
    #     user = get_user(creator)
    #     if not user:
    #         raise ValueError(f"User '{creator}' does not exist")

    #     post_id = f"post{uuid.uuid4().hex[:8]}"
    #     post_data = {
    #         "creator": creator,
    #         "content": content,
    #         "revoked": False,
    #         "shared_from": shared_from,  # only for shares/quotes
    #         "parent_id": parent_id,      # only for comments
    #         "quote": quote,
    #         "type": post_type,           # new field
    #         "timestamp": datetime.now().isoformat()
    #     }

    #     self.save_post(post_id, post_data)

    #     # Save reference in user profile
    #     if post_type == "comment":
    #         target = "comments"
    #     elif post_type in ("share", "quote"):
    #         target = "shared"
    #     else:
    #         target = "posts"

    #     user.setdefault(target, []).append(post_id)
    #     update_user(creator, user)

    #     return post_id


    def create_post(
        self,
        creator,
        content,
        shared_from=None,
        quote=False,
        post_type="post",
        parent_id=None,
    ):

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
            user.setdefault(target, []).append(obj.id)
            update_user(user["username"], user)

        return obj.id

    def delete_post(self, post_id, username):
        post = self.read_post(post_id)
        if post.get("creator") != username:
            raise PermissionError("Cannot delete another user's post")
        post["revoked"] = True
        self.save_post(post_id, post)

    # ---------------- USERS ----------------
    def user_exists(self, username):
        return get_user(username) is not None

    # ---------------- ROOMS ----------------
    def room_path(self, name):
        return ROOMS_DIR / f"{name}.json"

    def list_rooms(self):
        return sorted((p.stem for p in ROOMS_DIR.glob("*.json")))

    def _write_room(self, room):
        self.room_path(room["name"]).write_text(json.dumps(room, indent=4))

    def _read_room(self, name):
        path = self.room_path(name)
        if not path.exists():
            return None

        room = json.loads(path.read_text())

        if room.get("ephemeral") and time.time() > room["expires_at"]:
            path.unlink(missing_ok=True)
            return None

        return room

    def create_room(self, name, creator, private=False, ttl=None):
        if not self.user_exists(creator):
            raise ValueError(f"User '{creator}' does not exist")

        if self.room_path(name).exists():
            raise ValueError("Room exists")

        room = {
            "name": name,
            "type": "private" if private else "public",
            "owner": creator,
            "moderators": [],
            "members": [creator],
            "invites": [],
            "banned": [],
            "muted": {},
            "messages": [],
            "ephemeral": bool(ttl),
            "expires_at": time.time() + ttl if ttl else None,
        }

        self._write_room(room)

    def join_room(self, name, user, re_encrypt_old=False):
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self._read_room(name)
        if not room:
            raise ValueError("Room not found")

        if user in room.get("banned", []):
            raise PermissionError("You are banned from this room")
        if room["type"] == "private":
            if user != room["owner"] and user not in room["invites"]:
                raise PermissionError("Invite required")

        if user not in room["members"]:
            room["members"].append(user)
            if re_encrypt_old:
                self._encrypt_old_messages_for_new_user(room, user)

        self._write_room(room)

    def invite(self, room_name, user):
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self._read_room(room_name)

        if room is None:
            raise ValueError(f"Room '{room_name}' does not exist")

        if user not in room["invites"]:
            room["invites"].append(user)

        self._write_room(room)

    # ---------------- ROOM MESSAGES ----------------
    def say(self, room_name, sender, message):
        room = self._read_room(room_name)
        if not room or sender not in room["members"]:
            raise PermissionError(
                "Cannot send message to a room you are not a member of"
            )

        # ---- MUTE ENFORCEMENT ----
        muted = room.get("muted", {}).get(sender)
        if muted:
            if muted == "perma":
                raise PermissionError("You are muted in this room")
            if time.time() < muted.get("until", 0):
                raise PermissionError("You are muted in this room")
            else:
                # mute expired → clean it
                del room["muted"][sender]
                self._write_room(room)

        msg_bytes = message.encode()
        encrypted = {}

        for member in room["members"]:
            _, pub_key = load_or_create_keys(member)
            encrypted_blob = pub_key.encrypt(
                msg_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            encrypted[member] = encrypted_blob.hex()

        room["messages"].append(
            {"sender": sender, "timestamp": int(time.time()), "encrypted": encrypted}
        )

        self._write_room(room)

    def read_messages(self, room_name, username, start=0, limit=10):
        room = self._read_room(room_name)
        if not room or username not in room["members"]:
            return [], 0

        private_key, _ = load_or_create_keys(username)
        visible = []

        for msg in room["messages"]:
            if username not in msg["encrypted"]:
                continue
            try:
                decrypted = private_key.decrypt(
                    bytes.fromhex(msg["encrypted"][username]),
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None,
                    ),
                )
                visible.append(
                    {
                        "sender": msg["sender"],
                        "timestamp": msg["timestamp"],
                        "content": decrypted.decode(),
                    }
                )
            except:
                continue

        total = len(visible)
        return visible[start : start + limit], total

    # ---------------- CHATS (DMs) ----------------
    def chat_path(self, name):
        return CHATS_DIR / f"{name}.json"

    def list_chats(self):
        return sorted((c.stem for c in CHATS_DIR.glob("*.json")))

    def create_chat(self, chat_name, user_a, user_b):
        if user_a == user_b:
            raise ValueError("Cannot chat with yourself")
        if not self.user_exists(user_a) or not self.user_exists(user_b):
            raise ValueError("Both users must exist")

        members = sorted([user_a, user_b])
        name = "__".join(members)
        path = self.chat_path(name)
        if path.exists():
            return name

        chat = {
            "name": name,
            "members": members,
            "messages": [],
            "created_at": time.time(),
        }
        self._write_json(path, chat)
        return name

    def read_chat(self, name):
        return self._read_json(self.chat_path(name))

    # def chat_say(self, chat_name, sender, message):
    #     chat = self.read_chat(chat_name)
    #     if not chat or sender not in chat["members"]:
    #         raise PermissionError("Cannot send message")

    #     msg_bytes = message.encode()
    #     encrypted = {}

    #     for member in chat["members"]:
    #         _, pub_key = load_or_create_keys(member)
    #         encrypted_blob = pub_key.encrypt(
    #             msg_bytes,
    #             padding.OAEP(
    #                 mgf=padding.MGF1(algorithm=hashes.SHA256()),
    #                 algorithm=hashes.SHA256(),
    #                 label=None,
    #             ),
    #         )
    #         encrypted[member] = encrypted_blob.hex()

    #     chat["messages"].append(
    #         {"sender": sender, "timestamp": int(time.time()), "encrypted": encrypted}
    #     )

    #     self._write_json(self.chat_path(chat_name), chat)

    def chat_say(self, chat_name, sender, message):
        user = get_user(sender)
        if not user:
            raise PermissionError("Cannot send message")

        obj = BeepObject.create_object(
            type_="message",
            author_pubkey=user["pubkey"],
            content=message,
            meta={"chat": chat_name},
        )

        save_object(obj.to_dict())

        # optional: still store in legacy chat file for now
        chat = self.read_chat(chat_name)
        if chat:
            chat["messages"].append(
                {
                    "id": obj.id,
                    "sender": sender,
                    "timestamp": obj.timestamp,
                    "content": message,
                }
            )
            self._write_json(self.chat_path(chat_name), chat)

    def chat_read_messages(self, chat_name, user, start=0, limit=10):
        chat = self.read_chat(chat_name)
        if not chat or user not in chat["members"]:
            return [], 0

        visible = []

        for msg in chat["messages"]:
            if "content" in msg:
                visible.append(
                    {
                        "sender": msg["sender"],
                        "timestamp": msg["timestamp"],
                        "content": msg["content"],
                    }
                )
                continue

            if user not in msg.get("encrypted", {}):
                continue

            try:
                priv_key, _ = load_or_create_keys(user)
                decrypted = priv_key.decrypt(
                    bytes.fromhex(msg["encrypted"][user]),
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None,
                    ),
                )
                visible.append(
                    {
                        "sender": msg["sender"],
                        "timestamp": msg["timestamp"],
                        "content": decrypted.decode(),
                    }
                )
            except Exception:
                continue

        total = len(visible)
        return visible[start : start + limit], total

    # ----------- ENCRYPTION HELPERS -----------
    def _encrypt_old_messages_for_new_user(self, container, new_user):
        _, pub_key = load_or_create_keys(new_user)

        for msg in container["messages"]:
            if new_user in msg["encrypted"]:
                continue

            sender = msg["sender"]
            priv_key, _ = load_or_create_keys(sender)
            decrypted = priv_key.decrypt(
                bytes.fromhex(msg["encrypted"][sender]),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            encrypted_blob = pub_key.encrypt(
                decrypted,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            msg["encrypted"][new_user] = encrypted_blob.hex()
