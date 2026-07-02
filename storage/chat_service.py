# storage/chat_service.py
"""Private chat service built on synced encrypted objects."""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.identity import resolve_username
from core.object import BeepObject
from core.types import ChatMessage, ChatRecord, RecipientKeyInfo
from storage.crypto import (
    can_decrypt_private_message,
    decrypt_private_message,
    encrypt_for_recipients,
)
from storage.atomic import atomic_write_json, read_json_with_backup
from storage.ciphers import decode_text, encode_text
from storage.objects import query_objects, save_object
from storage.profile import get_user, get_user_by_pubkey

CHATS_DIR = Path.home() / ".beep" / "beep_storage" / "chats"
CHAT_INDEX_FILE = CHATS_DIR / "index.json"
CHATS_DIR.mkdir(parents=True, exist_ok=True)


class ChatService:
    """Manage private conversations between users."""

    def user_exists(self, username: str) -> bool:
        """Return whether a username resolves to a known user."""

        return get_user(username) is not None

    def user_pubkey(self, username: str) -> str:
        """Resolve the public key for a username."""

        user = get_user(username)
        if user is None:
            raise ValueError(f"User '{username}' does not exist")
        return user["pubkey"]

    def list_chats(self, username: str | None = None) -> list[str]:
        """List known chat IDs or counterpart usernames for a user."""

        if username is None:
            chat_ids: set[str] = set()
            for obj in query_objects():
                if obj.get("type") not in {"chat", "dm"}:
                    continue
                chat_id = _string_meta_value(obj, "chat")
                if chat_id:
                    chat_ids.add(chat_id)
            return sorted(chat_ids)

        user_pubkey = self.user_pubkey(username)
        counterparts: set[str] = set(self._chat_index().values())

        for obj in query_objects(obj_type="dm"):
            if obj.get("author") == user_pubkey:
                continue
            encrypted = _dict_meta_value(obj, "encrypted")
            if encrypted is None:
                continue
            if not can_decrypt_private_message(username, encrypted):
                continue
            counterparts.add(resolve_username(obj["author"]))

        return sorted(counterparts)

    def create_chat(self, chat_name: str | None, user_a: str, user_b: str) -> str:
        """Create the canonical chat object if needed and return its ID."""

        del chat_name
        if user_a == user_b:
            raise ValueError("Cannot chat with yourself")
        if not self.user_exists(user_a) or not self.user_exists(user_b):
            raise ValueError("Both users must exist")

        participants = self.chat_participant_pubkeys(user_a, user_b)
        chat_id = self.chat_id_from_pubkeys(participants)

        if not any(
            _string_meta_value(obj, "chat") == chat_id
            for obj in query_objects(obj_type="chat")
        ):
            chat_obj = BeepObject.create_object(
                type_="chat",
                author_pubkey=participants[0],
                content="[private chat]",
                meta={"chat": chat_id},
            )
            save_object(chat_obj.to_dict())

        self.remember_chat(chat_id, user_b)
        return chat_id

    def read_chat(self, name: str) -> ChatRecord:
        """Return a rendered chat record shell for the given chat."""

        return {
            "name": name,
            "members": [],
            "messages": [],
        }

    def chat_say(
        self,
        chat_peer: str,
        sender: str,
        message: str,
        *,
        cipher_profile: str | None = None,
    ) -> None:
        """Send an encrypted direct message."""

        if not self.user_exists(sender) or not self.user_exists(chat_peer):
            raise PermissionError("Cannot send message")

        participants = self.chat_participant_pubkeys(sender, chat_peer)
        chat_id = self.chat_id_from_pubkeys(participants)
        self.create_chat(None, sender, chat_peer)
        self.remember_chat(chat_id, chat_peer)

        meta: dict[str, object] = {"chat": chat_id}
        if cipher_profile:
            message, cipher = encode_text(message, cipher_profile)
            meta.update(
                {
                    "pml_version": 1,
                    "cipher_profile": cipher["profile"],
                    "cipher_version": cipher["version"],
                    "cipher_fingerprint": cipher["fingerprint"],
                }
            )

        recipient_keys = self.recipient_key_map(participants)
        encrypted = encrypt_for_recipients(message, recipient_keys)
        meta["encrypted"] = encrypted

        obj = BeepObject.create_object(
            type_="dm",
            author_pubkey=self.user_pubkey(sender),
            content="[encrypted]",
            meta=meta,
        )
        save_object(obj.to_dict())

    def chat_read_messages(
        self,
        chat_peer: str,
        user: str,
        start: int = 0,
        limit: int = 10,
    ) -> tuple[list[ChatMessage], int]:
        """Read visible chat messages for a user."""

        if not self.user_exists(user) or not self.user_exists(chat_peer):
            return [], 0

        participants = self.chat_participant_pubkeys(user, chat_peer)
        chat_id = self.chat_id_from_pubkeys(participants)
        visible: list[ChatMessage] = []

        for msg in query_objects(obj_type="dm"):
            if _string_meta_value(msg, "chat") != chat_id:
                continue

            encrypted = _dict_meta_value(msg, "encrypted")
            if encrypted is None:
                continue
            if not can_decrypt_private_message(user, encrypted):
                continue

            try:
                content = decrypt_private_message(user, encrypted)
            except Exception:
                continue
            content = self._decode_pml_content(msg, content)

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

    def _decode_pml_content(self, msg: dict[str, object], content: str) -> str:
        """Decode PML content when the local profile is available."""

        meta = msg.get("meta")
        if not isinstance(meta, dict):
            return content
        profile = meta.get("cipher_profile")
        version = meta.get("cipher_version")
        if not isinstance(profile, str):
            return content
        decoded, ok = decode_text(content, profile, version if isinstance(version, int) else None)
        return decoded if ok else content

    def chat_participant_pubkeys(self, user_a: str, user_b: str) -> list[str]:
        """Return sorted participant public keys for a chat."""

        return sorted([self.user_pubkey(user_a), self.user_pubkey(user_b)])

    def chat_id_from_pubkeys(self, pubkeys: list[str]) -> str:
        """Derive a stable opaque chat ID from participant pubkeys."""

        digest = hashlib.sha256("|".join(sorted(pubkeys)).encode("utf-8")).hexdigest()
        return f"dm_{digest[:24]}"

    def recipient_key_map(self, recipient_pubkeys: list[str]) -> dict[str, RecipientKeyInfo]:
        """Build the encryption key map for chat participants."""

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

    def _chat_index(self) -> dict[str, str]:
        """Load the local chat peer index."""

        raw = read_json_with_backup(CHAT_INDEX_FILE, default={})
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            chat_id: peer
            for chat_id, peer in raw.items()
            if isinstance(chat_id, str) and isinstance(peer, str)
        }

    def remember_chat(self, chat_id: str, peer_username: str) -> None:
        """Remember the last known peer name for a chat ID."""

        index = self._chat_index()
        if index.get(chat_id) == peer_username:
            return
        index[chat_id] = peer_username
        atomic_write_json(CHAT_INDEX_FILE, index, indent=4)


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
