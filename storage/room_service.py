# storage/room_service.py
"""Room service built on synced encrypted objects."""

from __future__ import annotations

import hashlib
import time

from core.identity import resolve_username
from core.object import BeepObject
from core.types import RecipientKeyInfo, RoomMessage, RoomMuteState, RoomState
from storage.crypto import (
    can_decrypt_private_message,
    decrypt_private_message,
    encrypt_for_recipients,
)
from storage.objects import query_objects, save_object
from storage.profile import (
    get_encryption_fingerprint,
    get_rsa_fingerprint,
    get_user,
    get_user_by_pubkey,
)


class RoomService:
    """Manage room lifecycle, membership, and encrypted room messages."""

    def user_exists(self, username: str) -> bool:
        """Return whether a username resolves to a known user."""

        return get_user(username) is not None

    def user_pubkey(self, username: str) -> str:
        """Resolve the public key for a username."""

        user = get_user(username)
        if user is None:
            raise ValueError(f"User '{username}' does not exist")
        return user["pubkey"]

    def list_rooms(self) -> list[str]:
        """List non-expired, non-dissolved rooms."""

        rooms: list[str] = []
        seen: set[str] = set()

        for obj in query_objects(obj_type="room"):
            room_name = obj.get("content")
            if not isinstance(room_name, str) or room_name in seen:
                continue
            if self.build_room_state(room_name) is None:
                continue
            seen.add(room_name)
            rooms.append(room_name)

        return sorted(rooms)

    def create_room(
        self,
        name: str,
        creator: str,
        private: bool = False,
        ttl: float | None = None,
    ) -> None:
        """Create a new room object."""

        if not self.user_exists(creator):
            raise ValueError(f"User '{creator}' does not exist")
        if self.build_room_state(name) is not None:
            raise ValueError("Room exists")

        creator_user = get_user(creator)
        if creator_user is None:
            raise ValueError(f"User '{creator}' does not exist")

        normalized_ttl = int(ttl) if ttl is not None else None
        room_id = self.make_room_id(creator_user["pubkey"], name)
        room_obj = BeepObject.create_object(
            type_="room",
            author_pubkey=creator_user["pubkey"],
            content=name,
            meta={
                "room_id": room_id,
                "private": bool(private),
                "ttl": normalized_ttl,
                "owner_pubkey": creator_user["pubkey"],
                "key_epoch": 1,
            },
        )
        if not save_object(room_obj.to_dict()):
            raise ValueError("Room could not be saved")

    def join_room(
        self,
        name: str,
        user: str,
        re_encrypt_old: bool = False,
    ) -> str:
        """Join a room if access rules allow it."""

        del re_encrypt_old
        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self.build_room_state(name)
        if room is None:
            raise ValueError("Room not found")

        user_profile = get_user(user)
        if user_profile is None:
            raise ValueError(f"User '{user}' does not exist")
        user_pubkey = user_profile["pubkey"]
        supported_key_ids = [
            key_id
            for key_id in (
                get_encryption_fingerprint(user_pubkey),
                get_rsa_fingerprint(user_pubkey),
            )
            if key_id is not None
        ]
        user_key_id = supported_key_ids[0] if supported_key_ids else None

        if user_pubkey in room["banned"]:
            raise PermissionError("You are banned from this room")
        if room["type"] == "private":
            invited_key_id = room["invited"].get(user_pubkey)
            if user_pubkey != room["owner_pubkey"] and invited_key_id is None:
                raise PermissionError("Invite required")
            if invited_key_id and invited_key_id not in supported_key_ids:
                raise PermissionError(
                    "Invite no longer matches your current encryption key"
                )
            if invited_key_id in supported_key_ids:
                user_key_id = invited_key_id

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

    def leave_room(self, name: str, user: str) -> str:
        """Leave a room while preserving owner membership semantics."""

        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self.build_room_state(name)
        if room is None:
            raise ValueError("Room not found")

        user_pubkey = self.user_pubkey(user)
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

    def dissolve_room(self, name: str, user: str) -> str:
        """Dissolve a room if the requester is the owner."""

        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self.build_room_state(name)
        if room is None:
            raise ValueError("Room not found")

        actor_pubkey = self.user_pubkey(user)
        if actor_pubkey != room["owner_pubkey"]:
            raise PermissionError("Only the room owner can dissolve the room")

        dissolve_obj = BeepObject.create_object(
            type_="room_event",
            author_pubkey=actor_pubkey,
            content="dissolve",
            meta={"room": room["room_id"], "action": "dissolve"},
        )
        save_object(dissolve_obj.to_dict())
        return "dissolved"

    def invite(self, room_name: str, user: str, actor: str | None = None) -> str:
        """Invite a user to a room."""

        if not self.user_exists(user):
            raise ValueError(f"User '{user}' does not exist")

        room = self.build_room_state(room_name)
        if room is None:
            raise ValueError(f"Room '{room_name}' does not exist")

        acting_user = actor or room["owner"]
        actor_pubkey = self.user_pubkey(acting_user)
        if actor_pubkey not in room["members"]:
            raise PermissionError("Only room members can invite users")

        target_pubkey = self.user_pubkey(user)
        if target_pubkey in room["members"]:
            return "already_member"

        target_key_id = get_encryption_fingerprint(
            target_pubkey
        ) or get_rsa_fingerprint(target_pubkey)
        if target_key_id is None:
            raise ValueError("Target user has no published encryption key")
        if room["invited"].get(target_pubkey) == target_key_id:
            return "already_invited"

        encrypted = encrypt_for_recipients(
            f"invite:{room['room_id']}",
            self.recipient_key_map([target_pubkey]),
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
                "encrypted": encrypted,
            },
        )
        save_object(invite_obj.to_dict())
        return "invited"

    def say(self, room_name: str, sender: str, message: str) -> None:
        """Send an encrypted room message."""

        room = self.build_room_state(room_name)
        if room is None:
            raise PermissionError("Room not found")

        sender_pubkey = self.user_pubkey(sender)
        if sender_pubkey not in room["members"]:
            raise PermissionError(
                "Cannot send message to a room you are not a member of"
            )

        muted = room["muted"].get(sender_pubkey)
        if muted:
            if muted == "perma":
                raise PermissionError("You are muted in this room")
            if isinstance(muted, dict) and time.time() < muted.get("until", 0.0):
                raise PermissionError("You are muted in this room")

        recipient_keys = self.recipient_key_map(sorted(room["members"]))
        encrypted = encrypt_for_recipients(message, recipient_keys)

        msg_obj = BeepObject.create_object(
            type_="room_message",
            author_pubkey=sender_pubkey,
            content="[encrypted]",
            meta={"room": room["room_id"], "encrypted": encrypted},
        )
        save_object(msg_obj.to_dict())

    def read_messages(
        self,
        room_name: str,
        username: str,
        start: int = 0,
        limit: int = 10,
    ) -> tuple[list[RoomMessage], int]:
        """Read visible room messages for a user."""

        room = self.build_room_state(room_name)
        if room is None:
            return [], 0

        user_pubkey = self.user_pubkey(username)
        if user_pubkey not in room["members"]:
            return [], 0

        visible: list[RoomMessage] = []

        for msg in query_objects(obj_type="room_message"):
            if _string_meta_value(msg, "room") != room["room_id"]:
                continue

            encrypted = _dict_meta_value(msg, "encrypted")
            if encrypted is None:
                continue
            if not can_decrypt_private_message(username, encrypted):
                continue

            try:
                content = decrypt_private_message(username, encrypted)
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

    def room_mod(
        self, room_name: str, actor: str, target: str, promote: bool = True
    ) -> str:
        """Promote or demote a room moderator."""

        room = self.build_room_state(room_name)
        if room is None:
            raise ValueError("Room not found")

        actor_pubkey = self.user_pubkey(actor)
        if actor_pubkey != room["owner_pubkey"]:
            raise PermissionError("only owner can manage moderators")

        target_pubkey = self.user_pubkey(target)
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

    def room_mute(
        self,
        room_name: str,
        actor: str,
        target: str,
        permanent: bool = False,
    ) -> str:
        """Mute a room member temporarily or permanently."""

        room = self.build_room_state(room_name)
        if room is None:
            raise ValueError("Room not found")

        actor_pubkey = self.user_pubkey(actor)
        if (
            actor_pubkey != room["owner_pubkey"]
            and actor_pubkey not in room["moderators"]
        ):
            raise PermissionError("permission denied")

        target_pubkey = self.user_pubkey(target)
        if target_pubkey == room["owner_pubkey"]:
            raise ValueError("cannot mute the room owner")
        existing_mute = room["muted"].get(target_pubkey)
        if permanent:
            if existing_mute == "perma":
                return "already_muted"
        elif isinstance(existing_mute, dict) and time.time() < existing_mute.get(
            "until", 0.0
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

    def room_unmute(self, room_name: str, actor: str, target: str) -> str:
        """Remove mute state from a room member."""

        room = self.build_room_state(room_name)
        if room is None:
            raise ValueError("Room not found")

        actor_pubkey = self.user_pubkey(actor)
        if (
            actor_pubkey != room["owner_pubkey"]
            and actor_pubkey not in room["moderators"]
        ):
            raise PermissionError("permission denied")

        target_pubkey = self.user_pubkey(target)
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

    def room_kick(self, room_name: str, actor: str, target: str) -> str:
        """Kick and ban a room member."""

        room = self.build_room_state(room_name)
        if room is None:
            raise ValueError("Room not found")

        actor_pubkey = self.user_pubkey(actor)
        if (
            actor_pubkey != room["owner_pubkey"]
            and actor_pubkey not in room["moderators"]
        ):
            raise PermissionError("permission denied")

        target_pubkey = self.user_pubkey(target)
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

    def make_room_id(self, owner_pubkey: str, name: str) -> str:
        """Derive a unique opaque room ID."""

        seed = f"{owner_pubkey}:{name}:{time.time_ns()}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return f"room_{digest[:24]}"

    def recipient_key_map(
        self, recipient_pubkeys: list[str]
    ) -> dict[str, RecipientKeyInfo]:
        """Build the encryption key map for room recipients."""

        recipient_keys: dict[str, RecipientKeyInfo] = {}
        missing_keys: list[str] = []
        for recipient_pubkey in recipient_pubkeys:
            recipient = get_user_by_pubkey(recipient_pubkey)
            if recipient is None:
                missing_keys.append(recipient_pubkey)
                continue
            recipient_keys[recipient_pubkey] = {
                "enc_pubkey": recipient.get("enc_pubkey"),
                "enc_fingerprint": recipient.get("enc_fingerprint"),
                "rsa_pubkey": recipient.get("rsa_pubkey"),
                "rsa_fingerprint": recipient.get("rsa_fingerprint"),
            }

        if missing_keys:
            print(
                "[WARN] Could not encrypt for "
                f"{len(missing_keys)} member(s) - their keys are not available. "
                "Message will reach other members."
            )

        return recipient_keys

    def get_room_object(self, name_or_id: str):
        """Find the canonical room object by name or room ID."""

        room_objects = sorted(
            query_objects(obj_type="room"),
            key=lambda obj: obj["timestamp"],
            reverse=True,
        )
        for obj in room_objects:
            if obj.get("content") == name_or_id:
                return obj
            if _string_meta_value(obj, "room_id") == name_or_id:
                return obj
            if _string_meta_value(obj, "room") == name_or_id:
                return obj
        return None

    def legacy_target_pubkey(self, meta: dict[str, object]) -> str | None:
        """Resolve target public keys from old and new event formats."""

        target_pubkey = meta.get("target_pubkey")
        if isinstance(target_pubkey, str) and target_pubkey:
            return target_pubkey

        target = meta.get("target")
        if isinstance(target, str):
            profile = get_user(target)
            if profile is not None:
                return profile["pubkey"]
        return None

    def build_room_state(self, name_or_id: str) -> RoomState | None:
        """Rebuild room state by replaying room and room_event objects."""

        room_obj = self.get_room_object(name_or_id)
        if room_obj is None:
            return None

        room_id = _string_meta_value(room_obj, "room_id") or room_obj["content"]
        ttl_value = room_obj.get("meta", {}).get("ttl")
        ttl = float(ttl_value) if isinstance(ttl_value, (int, float)) else None
        expires_at = room_obj["timestamp"] + ttl if ttl is not None else None
        if expires_at is not None and time.time() > expires_at:
            return None

        owner_pubkey = (
            _string_meta_value(room_obj, "owner_pubkey") or room_obj["author"]
        )
        room: RoomState = {
            "room_id": room_id,
            "name": room_obj["content"],
            "type": "private" if _bool_meta_value(room_obj, "private") else "public",
            "owner": resolve_username(owner_pubkey),
            "owner_pubkey": owner_pubkey,
            "moderators": set(),
            "members": {owner_pubkey},
            "invited": {},
            "banned": set(),
            "muted": {},
            "ephemeral": ttl is not None,
            "expires_at": expires_at,
            "dissolved": False,
        }

        room_name = room_obj["content"]
        events = sorted(
            [
                obj
                for obj in query_objects(obj_type="room_event")
                if _string_meta_value(obj, "room") in {room_id, room_name}
            ],
            key=lambda obj: obj["timestamp"],
        )

        for event in events:
            meta = event.get("meta", {})
            if not isinstance(meta, dict):
                continue
            action = meta.get("action")
            if not isinstance(action, str):
                continue
            actor_pubkey = event["author"]
            target_pubkey = self.legacy_target_pubkey(meta)
            target_key_id = meta.get("target_key_id")

            if action == "invite":
                if actor_pubkey not in room["members"]:
                    continue
                invited_pubkey = self.legacy_target_pubkey(meta)
                invited_key_id = (
                    target_key_id if isinstance(target_key_id, str) else None
                )
                if invited_key_id is None:
                    encrypted = meta.get("encrypted")
                    if isinstance(encrypted, dict):
                        keys = encrypted.get("keys")
                        if isinstance(keys, list):
                            for slot in keys:
                                if isinstance(slot, dict):
                                    slot_key_id = slot.get("key_id")
                                    if isinstance(slot_key_id, str) and slot_key_id:
                                        invited_key_id = slot_key_id
                                        break
                if invited_pubkey and invited_key_id:
                    room["invited"][invited_pubkey] = invited_key_id
                continue

            if action == "dissolve":
                if actor_pubkey != owner_pubkey:
                    continue
                room["dissolved"] = True
                continue

            if target_pubkey is None:
                continue

            if action == "join":
                if actor_pubkey != target_pubkey:
                    continue
                join_key_id = target_key_id if isinstance(target_key_id, str) else None
                if room["type"] == "private" and target_pubkey != owner_pubkey:
                    if target_pubkey not in room["invited"]:
                        continue
                    if room["invited"][target_pubkey] != join_key_id:
                        continue
                if target_pubkey not in room["banned"]:
                    room["members"].add(target_pubkey)
            elif action == "leave":
                if actor_pubkey != target_pubkey:
                    continue
                if target_pubkey in room["members"] and target_pubkey != owner_pubkey:
                    room["members"].remove(target_pubkey)
            elif action == "mod":
                if actor_pubkey != owner_pubkey:
                    continue
                room["moderators"].add(target_pubkey)
            elif action == "unmod":
                if actor_pubkey != owner_pubkey:
                    continue
                room["moderators"].discard(target_pubkey)
            elif action == "mute":
                if actor_pubkey != owner_pubkey and actor_pubkey not in room["moderators"]:
                    continue
                permanent = meta.get("permanent")
                if permanent is True:
                    room["muted"][target_pubkey] = "perma"
                else:
                    until = meta.get("until")
                    until_value = (
                        float(until) if isinstance(until, (int, float)) else 0.0
                    )
                    room["muted"][target_pubkey] = {"until": until_value}
            elif action == "unmute":
                if actor_pubkey != owner_pubkey and actor_pubkey not in room["moderators"]:
                    continue
                room["muted"].pop(target_pubkey, None)
            elif action == "kick":
                if actor_pubkey != owner_pubkey and actor_pubkey not in room["moderators"]:
                    continue
                room["members"].discard(target_pubkey)
                room["banned"].add(target_pubkey)

        if room["dissolved"]:
            return None

        return room


def _string_meta_value(obj: dict[str, object], key: str) -> str | None:
    """Extract a string metadata field from an object-like mapping."""

    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get(key)
    return value if isinstance(value, str) and value else None


def _dict_meta_value(obj: dict[str, object], key: str) -> dict[str, object] | None:
    """Extract a metadata sub-dictionary from an object-like mapping."""

    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get(key)
    return value if isinstance(value, dict) else None


def _bool_meta_value(obj: dict[str, object], key: str) -> bool:
    """Extract a boolean metadata field from an object-like mapping."""

    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return False
    return meta.get(key) is True
