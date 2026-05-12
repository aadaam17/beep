import hashlib
import json
import time
from pathlib import Path

from core.identity import resolve_username
from core.object import BeepObject
from storage.crypto import (
    decrypt_from_envelope,
    encrypt_for_recipients,
    load_or_create_keys,
)
from storage.objects import get_object, query_objects, save_object
from storage.profile import (
    get_encryption_pubkey,
    get_rsa_fingerprint,
    get_user,
    get_user_by_pubkey,
    update_user,
)

STORAGE_DIR = Path.home() / ".beep" / "beep_storage"
POSTS_DIR = STORAGE_DIR / "posts"
ROOMS_DIR = STORAGE_DIR / "rooms"
USER_DIR = STORAGE_DIR / "users"
CHATS_DIR = STORAGE_DIR / "chats"
CHAT_INDEX_FILE = CHATS_DIR / "index.json"

for path in (STORAGE_DIR, POSTS_DIR, ROOMS_DIR, USER_DIR, CHATS_DIR):
    path.mkdir(exist_ok=True)


class BeepFS:
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

    def list_posts(self, only_existing_users: bool = False):
        posts = query_objects(obj_type="post")

        if not only_existing_users:
            return [obj["id"] for obj in posts]

        return [obj["id"] for obj in posts if get_user_by_pubkey(obj["author"])]

    def list_followed_posts(self, username):
        user = get_user(username)
        if not user:
            return []

        followed = set(user.get("following", []))
        return [
            post_id
            for post_id in self.list_posts(only_existing_users=True)
            if self.read_post(post_id).get("creator") in followed
        ]

    def post_path(self, post_id):
        return POSTS_DIR / f"{post_id}.json"

    def read_post(self, post_id):
        obj = get_object(post_id)
        if not obj:
            return {
                "creator": None,
                "content": "[missing]",
                "revoked": True,
                "shared_from": None,
                "type": None,
            }

        return {
            "creator": obj["author"],
            "content": obj["content"],
            "timestamp": obj["timestamp"],
            "type": obj["type"],
            "revoked": False,
            "shared_from": obj.get("meta", {}).get("shared_from"),
            "parent_id": obj.get("meta", {}).get("parent_id"),
            "quote": obj.get("meta", {}).get("quote", False),
        }

    def save_post(self, post_id, data):
        self._write_json(self.post_path(post_id), data)

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
            if user["username"] in self._local_usernames():
                update_user(user["username"], user)

        return obj.id

    def delete_post(self, post_id, username):
        post = self.read_post(post_id)
        if post.get("creator") != username:
            raise PermissionError("Cannot delete another user's post")
        post["revoked"] = True
        self.save_post(post_id, post)

    def user_exists(self, username):
        return get_user(username) is not None

    def room_path(self, name):
        return ROOMS_DIR / f"{name}.json"

    def list_rooms(self):
        rooms = []
        seen = set()

        for obj in query_objects(obj_type="room"):
            room_name = obj.get("content")
            if not room_name or room_name in seen:
                continue
            if not self._build_room_state(room_name):
                continue
            seen.add(room_name)
            rooms.append(room_name)

        return sorted(rooms)

    def _write_room(self, room):
        return room

    def _read_room(self, name):
        return self._build_room_state(name)

    def create_room(self, name, creator, private=False, ttl=None):
        if not self.user_exists(creator):
            raise ValueError(f"User '{creator}' does not exist")
        if self._build_room_state(name):
            raise ValueError("Room exists")

        creator_user = get_user(creator)
        room_id = self._make_room_id(creator_user["pubkey"], name)
        room_obj = BeepObject.create_object(
            type_="room",
            author_pubkey=creator_user["pubkey"],
            content=name,
            meta={
                "room_id": room_id,
                "private": bool(private),
                "ttl": ttl,
                "owner_pubkey": creator_user["pubkey"],
                "key_epoch": 1,
            },
        )
        save_object(room_obj.to_dict())

    def join_room(self, name, user, re_encrypt_old=False):
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self._build_room_state(name)
        if not room:
            raise ValueError("Room not found")

        user_profile = get_user(user)
        user_pubkey = user_profile["pubkey"]
        user_key_id = get_rsa_fingerprint(user_pubkey)

        if user_pubkey in room["banned"]:
            raise PermissionError("You are banned from this room")
        if room["type"] == "private":
            invited_key_id = room["invited"].get(user_pubkey)
            if user_pubkey != room["owner_pubkey"] and not invited_key_id:
                raise PermissionError("Invite required")
            if invited_key_id and invited_key_id != user_key_id:
                raise PermissionError(
                    "Invite no longer matches your current encryption key"
                )

        if user_pubkey in room["members"]:
            return "already_member"

        join_obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=user_pubkey,
            content="join",
            meta={
                "room": room["room_id"],
                "action": "join",
                "target_pubkey": user_pubkey,
                "target_key_id": user_key_id,
            },
        )
        save_object(join_obj.to_dict())
        return "joined"

    def leave_room(self, name, user):
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self._build_room_state(name)
        if not room:
            raise ValueError("Room not found")

        user_pubkey = self._user_pubkey(user)
        if user_pubkey == room["owner_pubkey"]:
            return "owner_exit"
        if user_pubkey not in room["members"]:
            return "not_member"

        leave_obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=user_pubkey,
            content="leave",
            meta={
                "room": room["room_id"],
                "action": "leave",
                "target_pubkey": user_pubkey,
            },
        )
        save_object(leave_obj.to_dict())
        return "left"

    def dissolve_room(self, name, user):
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self._build_room_state(name)
        if not room:
            raise ValueError("Room not found")

        actor_pubkey = self._user_pubkey(user)
        if actor_pubkey != room["owner_pubkey"]:
            raise PermissionError("Only the room owner can dissolve the room")

        dissolve_obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content="dissolve",
            meta={
                "room": room["room_id"],
                "action": "dissolve",
            },
        )
        save_object(dissolve_obj.to_dict())
        return "dissolved"

    def invite(self, room_name, user, actor=None):
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self._build_room_state(room_name)
        if not room:
            raise ValueError(f"Room '{room_name}' does not exist")

        actor = actor or room["owner"]
        actor_pubkey = self._user_pubkey(actor)
        if actor_pubkey not in room["members"]:
            raise PermissionError("Only room members can invite users")

        target_pubkey = self._user_pubkey(user)
        if target_pubkey in room["members"]:
            return "already_member"

        target_key_id = get_rsa_fingerprint(target_pubkey)
        if room["invited"].get(target_pubkey) == target_key_id:
            return "already_invited"

        encrypted = encrypt_for_recipients(
            f"invite:{room['room_id']}",
            self._recipient_key_map([target_pubkey]),
        )

        invite_obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content="invite",
            meta={
                "room": room["room_id"],
                "action": "invite",
                "target_pubkey": target_pubkey,
                "target_key_id": target_key_id,
                "encrypted": {
                    "nonce": encrypted["nonce"],
                    "ciphertext": encrypted["ciphertext"],
                    "keys": encrypted["keys"],
                },
            },
        )
        save_object(invite_obj.to_dict())
        return "invited"

    def say(self, room_name, sender, message):
        room = self._build_room_state(room_name)
        if not room:
            raise PermissionError("Room not found")

        sender_pubkey = self._user_pubkey(sender)
        if sender_pubkey not in room["members"]:
            raise PermissionError(
                "Cannot send message to a room you are not a member of"
            )

        muted = room["muted"].get(sender_pubkey)
        if muted:
            if muted == "perma":
                raise PermissionError("You are muted in this room")
            if time.time() < muted.get("until", 0):
                raise PermissionError("You are muted in this room")

        recipient_keys = self._recipient_key_map(room["members"])
        encrypted = encrypt_for_recipients(message, recipient_keys)

        msg_obj = BeepObject.create_object(
            type_="room_message",
            author_pubkey=sender_pubkey,
            content="[encrypted]",
            meta={
                "room": room["room_id"],
                "encrypted": {
                    "nonce": encrypted["nonce"],
                    "ciphertext": encrypted["ciphertext"],
                    "keys": encrypted["keys"],
                },
            },
        )
        save_object(msg_obj.to_dict())

    def read_messages(self, room_name, username, start=0, limit=10):
        room = self._build_room_state(room_name)
        if not room:
            return [], 0

        user_pubkey = self._user_pubkey(username)
        if user_pubkey not in room["members"]:
            return [], 0

        private_key, _ = load_or_create_keys(username)
        current_key_id = get_rsa_fingerprint(user_pubkey)
        visible = []

        for msg in query_objects(obj_type="room_message"):
            if msg.get("meta", {}).get("room") != room["room_id"]:
                continue

            encrypted = msg.get("meta", {}).get("encrypted")
            if not encrypted:
                continue

            recipient_entry = self._find_key_slot(encrypted, current_key_id)
            if not recipient_entry:
                continue

            try:
                content = decrypt_from_envelope(
                    private_key,
                    {
                        "key": recipient_entry["key"],
                        "nonce": encrypted["nonce"],
                        "ciphertext": encrypted["ciphertext"],
                    },
                )
            except Exception:
                continue

            visible.append(
                {
                    "sender": resolve_username(msg["author"]),
                    "timestamp": msg["timestamp"],
                    "content": content,
                }
            )

        visible.sort(key=lambda item: item["timestamp"])
        total = len(visible)
        return visible[start : start + limit], total

    def list_chats(self, username=None):
        if username is None:
            chat_ids = set()
            for obj in query_objects():
                if obj.get("type") not in {"chat", "dm"}:
                    continue
                chat_id = obj.get("meta", {}).get("chat")
                if chat_id:
                    chat_ids.add(chat_id)
            return sorted(chat_ids)

        user_pubkey = self._user_pubkey(username)
        counterparts = set(self._chat_index().values())

        for obj in query_objects():
            if obj.get("type") != "dm":
                continue
            if obj.get("author") == user_pubkey:
                continue
            if not self._find_key_slot(
                obj.get("meta", {}).get("encrypted", {}),
                get_rsa_fingerprint(user_pubkey),
            ):
                continue
            counterparts.add(resolve_username(obj["author"]))

        return sorted(counterparts)

    def create_chat(self, chat_name, user_a, user_b):
        if user_a == user_b:
            raise ValueError("Cannot chat with yourself")
        if not self.user_exists(user_a) or not self.user_exists(user_b):
            raise ValueError("Both users must exist")

        participants = self._chat_participant_pubkeys(user_a, user_b)
        chat_id = self._chat_id_from_pubkeys(participants)

        if not any(
            obj.get("meta", {}).get("chat") == chat_id
            for obj in query_objects(obj_type="chat")
        ):
            chat_obj = BeepObject.create_object(
                type_="chat",
                author_pubkey=participants[0],
                content="[private chat]",
                meta={"chat": chat_id},
            )
            save_object(chat_obj.to_dict())

        self._remember_chat(chat_id, user_b)
        return chat_id

    def read_chat(self, name):
        return {"name": name, "members": [], "messages": []}

    def chat_say(self, chat_peer, sender, message):
        if not self.user_exists(sender):
            raise PermissionError("Cannot send message")
        if not self.user_exists(chat_peer):
            raise PermissionError("Cannot send message")

        participants = self._chat_participant_pubkeys(sender, chat_peer)
        chat_id = self._chat_id_from_pubkeys(participants)
        self.create_chat(None, sender, chat_peer)
        self._remember_chat(chat_id, chat_peer)

        recipient_keys = self._recipient_key_map(participants)
        encrypted = encrypt_for_recipients(message, recipient_keys)

        obj = BeepObject.create_object(
            type_="dm",
            author_pubkey=self._user_pubkey(sender),
            content="[encrypted]",
            meta={
                "chat": chat_id,
                "encrypted": {
                    "nonce": encrypted["nonce"],
                    "ciphertext": encrypted["ciphertext"],
                    "keys": encrypted["keys"],
                },
            },
        )
        save_object(obj.to_dict())

    def chat_read_messages(self, chat_peer, user, start=0, limit=10):
        if not self.user_exists(user) or not self.user_exists(chat_peer):
            return [], 0

        participants = self._chat_participant_pubkeys(user, chat_peer)
        user_pubkey = self._user_pubkey(user)
        chat_id = self._chat_id_from_pubkeys(participants)
        current_key_id = get_rsa_fingerprint(user_pubkey)
        private_key, _ = load_or_create_keys(user)
        visible = []

        for msg in query_objects(obj_type="dm"):
            if msg.get("meta", {}).get("chat") != chat_id:
                continue

            recipient_entry = self._find_key_slot(
                msg.get("meta", {}).get("encrypted", {}), current_key_id
            )
            if not recipient_entry:
                continue

            try:
                content = decrypt_from_envelope(
                    private_key,
                    {
                        "key": recipient_entry["key"],
                        "nonce": msg["meta"]["encrypted"]["nonce"],
                        "ciphertext": msg["meta"]["encrypted"]["ciphertext"],
                    },
                )
            except Exception:
                continue

            visible.append(
                {
                    "sender": resolve_username(msg["author"]),
                    "timestamp": msg["timestamp"],
                    "content": content,
                }
            )

        visible.sort(key=lambda item: item["timestamp"])
        total = len(visible)
        return visible[start : start + limit], total

    def room_mod(self, room_name, actor, target, promote=True):
        room = self._build_room_state(room_name)
        if not room:
            raise ValueError("Room not found")

        actor_pubkey = self._user_pubkey(actor)
        if actor_pubkey != room["owner_pubkey"]:
            raise PermissionError("only owner can manage moderators")

        target_pubkey = self._user_pubkey(target)
        if target_pubkey == room["owner_pubkey"]:
            raise ValueError("cannot change the room owner")

        action = "mod" if promote else "unmod"
        if promote and target_pubkey in room["moderators"]:
            return "already_mod"
        if not promote and target_pubkey not in room["moderators"]:
            return "not_mod"

        obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content=action,
            meta={
                "room": room["room_id"],
                "action": action,
                "target_pubkey": target_pubkey,
            },
        )
        save_object(obj.to_dict())
        return "promoted" if promote else "demoted"

    def room_mute(self, room_name, actor, target, permanent=False):
        room = self._build_room_state(room_name)
        if not room:
            raise ValueError("Room not found")

        actor_pubkey = self._user_pubkey(actor)
        if (
            actor_pubkey != room["owner_pubkey"]
            and actor_pubkey not in room["moderators"]
        ):
            raise PermissionError("permission denied")

        target_pubkey = self._user_pubkey(target)
        if target_pubkey == room["owner_pubkey"]:
            raise ValueError("cannot mute the room owner")
        existing_mute = room["muted"].get(target_pubkey)
        if permanent:
            if existing_mute == "perma":
                return "already_muted"
        elif isinstance(existing_mute, dict) and time.time() < existing_mute.get(
            "until", 0
        ):
            return "already_muted"

        obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content="mute",
            meta={
                "room": room["room_id"],
                "action": "mute",
                "target_pubkey": target_pubkey,
                "until": None if permanent else time.time() + 86400,
                "permanent": permanent,
            },
        )
        save_object(obj.to_dict())
        return "muted"

    def room_unmute(self, room_name, actor, target):
        room = self._build_room_state(room_name)
        if not room:
            raise ValueError("Room not found")

        actor_pubkey = self._user_pubkey(actor)
        if (
            actor_pubkey != room["owner_pubkey"]
            and actor_pubkey not in room["moderators"]
        ):
            raise PermissionError("permission denied")

        target_pubkey = self._user_pubkey(target)
        if target_pubkey not in room["muted"]:
            return "not_muted"

        obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content="unmute",
            meta={
                "room": room["room_id"],
                "action": "unmute",
                "target_pubkey": target_pubkey,
            },
        )
        save_object(obj.to_dict())
        return "unmuted"

    def room_kick(self, room_name, actor, target):
        room = self._build_room_state(room_name)
        if not room:
            raise ValueError("Room not found")

        actor_pubkey = self._user_pubkey(actor)
        if (
            actor_pubkey != room["owner_pubkey"]
            and actor_pubkey not in room["moderators"]
        ):
            raise PermissionError("permission denied")

        target_pubkey = self._user_pubkey(target)
        if target_pubkey == room["owner_pubkey"]:
            raise ValueError("cannot kick the room owner")
        if target_pubkey in room["banned"]:
            return "already_banned"
        if target_pubkey not in room["members"]:
            return "not_member"

        obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content="kick",
            meta={
                "room": room["room_id"],
                "action": "kick",
                "target_pubkey": target_pubkey,
            },
        )
        save_object(obj.to_dict())
        return "kicked"

    def _local_usernames(self):
        user_file = Path.home() / ".beep" / "beep_users.json"
        data = self._read_json(user_file, default={}) or {}
        return set(data.keys())

    def _user_pubkey(self, username):
        user = get_user(username)
        if not user:
            raise ValueError(f"User '{username}' does not exist")
        return user["pubkey"]

    def _chat_participant_pubkeys(self, user_a, user_b):
        return sorted([self._user_pubkey(user_a), self._user_pubkey(user_b)])

    def _chat_id_from_pubkeys(self, pubkeys):
        digest = hashlib.sha256("|".join(sorted(pubkeys)).encode("utf-8")).hexdigest()
        return f"dm_{digest[:24]}"

    def _make_room_id(self, owner_pubkey, name):
        seed = f"{owner_pubkey}:{name}:{time.time_ns()}"
        return f"room_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"

    def _recipient_key_map(self, recipient_pubkeys):
        recipient_keys = {}
        missing_keys = []
        for recipient_pubkey in recipient_pubkeys:
            rsa_pubkey = get_encryption_pubkey(recipient_pubkey)
            rsa_fingerprint = get_rsa_fingerprint(recipient_pubkey)
            if not rsa_pubkey or not rsa_fingerprint:
                # Skip recipients with missing keys instead of failing
                missing_keys.append(recipient_pubkey)
                continue
            recipient_keys[recipient_pubkey] = {
                "rsa_pubkey": rsa_pubkey,
                "rsa_fingerprint": rsa_fingerprint,
            }

        # Warn if some keys are missing, but allow message to be sent to available members
        if missing_keys:
            print(
                f"[WARN] Could not encrypt for {len(missing_keys)} member(s) - their keys are not available. Message will reach other members."
            )

        return recipient_keys

    def _chat_index(self):
        return self._read_json(CHAT_INDEX_FILE, default={}) or {}

    def _remember_chat(self, chat_id, peer_username):
        index = self._chat_index()
        if index.get(chat_id) == peer_username:
            return
        index[chat_id] = peer_username
        self._write_json(CHAT_INDEX_FILE, index)

    def _find_key_slot(self, encrypted_meta, key_id):
        slots = encrypted_meta.get("keys", [])
        if isinstance(slots, dict):
            for slot in slots.values():
                if slot.get("key_id") == key_id:
                    return slot
            return None

        for slot in slots:
            if slot.get("key_id") == key_id:
                return slot
        return None

    def _get_room_object(self, name_or_id):
        room_objects = query_objects(obj_type="room")

        for obj in room_objects:
            if obj.get("content") == name_or_id:
                return obj
            if obj.get("meta", {}).get("room_id") == name_or_id:
                return obj
            if obj.get("meta", {}).get("room") == name_or_id:
                return obj
        return None

    def _legacy_target_pubkey(self, meta):
        if meta.get("target_pubkey"):
            return meta["target_pubkey"]
        if meta.get("target"):
            target = get_user(meta["target"])
            if target:
                return target["pubkey"]
        return None

    def _build_room_state(self, name_or_id):
        room_obj = self._get_room_object(name_or_id)
        if not room_obj:
            return None

        room_id = room_obj.get("meta", {}).get("room_id") or room_obj.get("content")
        ttl = room_obj.get("meta", {}).get("ttl")
        expires_at = room_obj["timestamp"] + ttl if ttl else None
        if expires_at and time.time() > expires_at:
            return None

        owner_pubkey = (
            room_obj.get("meta", {}).get("owner_pubkey") or room_obj["author"]
        )
        room = {
            "room_id": room_id,
            "name": room_obj.get("content"),
            "type": "private" if room_obj.get("meta", {}).get("private") else "public",
            "owner": resolve_username(owner_pubkey),
            "owner_pubkey": owner_pubkey,
            "moderators": set(),
            "members": {owner_pubkey},
            "invited": {},
            "banned": set(),
            "muted": {},
            "ephemeral": bool(ttl),
            "expires_at": expires_at,
            "dissolved": False,
        }

        events = sorted(
            [
                obj
                for obj in query_objects(obj_type="room_event")
                if obj.get("meta", {}).get("room") in {room_id, room_obj.get("content")}
            ],
            key=lambda obj: obj["timestamp"],
        )

        for event in events:
            meta = event.get("meta", {})
            action = meta.get("action")
            target_pubkey = self._legacy_target_pubkey(meta)
            target_key_id = meta.get("target_key_id")

            if action == "invite":
                invited_pubkey = self._legacy_target_pubkey(meta)
                invited_key_id = meta.get("target_key_id")
                if not invited_key_id:
                    for slot in meta.get("encrypted", {}).get("keys", []):
                        if slot.get("key_id"):
                            invited_key_id = slot["key_id"]
                            break
                if invited_pubkey and invited_key_id:
                    room["invited"][invited_pubkey] = invited_key_id
                continue

            if action == "dissolve":
                room["dissolved"] = True
                continue

            if not target_pubkey:
                continue

            if action == "join":
                if room["type"] == "private" and target_pubkey != owner_pubkey:
                    if target_pubkey not in room["invited"]:
                        continue
                    if room["invited"][target_pubkey] != target_key_id:
                        continue
                if target_pubkey not in room["banned"]:
                    room["members"].add(target_pubkey)
            elif action == "leave":
                if target_pubkey in room["members"] and target_pubkey != owner_pubkey:
                    room["members"].remove(target_pubkey)
            elif action == "mod":
                room["moderators"].add(target_pubkey)
            elif action == "unmod":
                room["moderators"].discard(target_pubkey)
            elif action == "mute":
                if meta.get("permanent"):
                    room["muted"][target_pubkey] = "perma"
                else:
                    room["muted"][target_pubkey] = {"until": meta.get("until", 0)}
            elif action == "unmute":
                room["muted"].pop(target_pubkey, None)
            elif action == "kick":
                room["members"].discard(target_pubkey)
                room["banned"].add(target_pubkey)

        if room["dissolved"]:
            return None

        return room
