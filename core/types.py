# core/types.py
"""Shared typing primitives for the Beep codebase."""

from __future__ import annotations

from typing import NotRequired, Protocol, TypeAlias, TypedDict, Any

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
ObjectMeta: TypeAlias = dict[str, JSONValue]


class SessionRecord(TypedDict):
    """Persisted login session data."""

    username: str
    pubkey: str


class BeepObjectRecord(TypedDict):
    """Stored Beep object payload."""

    type: str
    author: str
    content: str
    timestamp: float
    meta: ObjectMeta
    id: str
    signature: str


class UserRecord(TypedDict):
    """Persisted local or discovered user profile data."""

    id: str
    username: str
    pubkey: str
    enc_pubkey: str
    enc_fingerprint: str
    key_derivation_version: int
    seed_fingerprint: str
    signing_scheme: str
    encryption_scheme: str
    password: str
    followers: list[str]
    following: list[str]
    posts: list[str]
    shared: list[str]
    iro_id: str | None
    rsa_pubkey: NotRequired[str]
    rsa_fingerprint: NotRequired[str]


class ChatMessage(TypedDict):
    """Rendered direct-message entry."""

    sender: str
    timestamp: float
    content: str


class PostView(TypedDict):
    """Rendered post view returned by the storage facade."""

    creator: str | None
    content: str
    revoked: bool
    shared_from: str | None
    type: str | None
    timestamp: NotRequired[float]
    parent_id: NotRequired[str | None]
    quote: NotRequired[bool]


class ChatRecord(TypedDict):
    """Rendered chat view."""

    name: str
    members: list[str]
    messages: list[ChatMessage]


class RoomMessage(TypedDict):
    """Rendered room message entry."""

    sender: str
    timestamp: float
    content: str


class RoomMuteWindow(TypedDict):
    """Temporary mute expiration window."""

    until: float


RoomMuteState: TypeAlias = str | RoomMuteWindow


class RoomState(TypedDict):
    """Reconstructed room state."""

    room_id: str
    name: str
    type: str
    owner: str
    owner_pubkey: str
    moderators: set[str]
    members: set[str]
    invited: dict[str, str]
    banned: set[str]
    muted: dict[str, RoomMuteState]
    ephemeral: bool
    expires_at: float | None
    dissolved: bool


class RecipientKeyInfo(TypedDict):
    """Encryption key material published for a recipient."""

    enc_pubkey: NotRequired[str]
    enc_fingerprint: NotRequired[str]
    rsa_pubkey: NotRequired[str]
    rsa_fingerprint: NotRequired[str]


class EncryptedKeySlot(TypedDict):
    """Recipient-specific wrapped key slot."""

    key: str
    key_id: str | None
    nonce: NotRequired[str]
    ephemeral_pubkey: NotRequired[str]


class EncryptedEnvelope(TypedDict):
    """Encrypted message envelope."""

    scheme: str
    nonce: str
    ciphertext: str
    keys: list[EncryptedKeySlot]


class RecoveryEnvelope(TypedDict):
    """Seed-based recovery envelope."""

    scheme: str
    nonce: str
    ciphertext: str


class IROPayload(TypedDict):
    """Decrypted identity root object payload."""

    version: int
    username: str | None
    owner_pubkey: str
    object_ids: list[str]
    post_ids: list[str]
    chat_ids: list[str]
    room_ids: list[str]
    peer_refs: list[str]
    legacy_rsa_private_pem: NotRequired[str]
    legacy_rsa_public_pem: NotRequired[str]


class ProfileMeta(TypedDict):
    """Published profile metadata."""

    username: str
    enc_pubkey: str
    enc_fingerprint: str
    key_derivation_version: int
    seed_fingerprint: str
    signing_scheme: str
    encryption_scheme: str
    rsa_pubkey: NotRequired[str]
    rsa_fingerprint: NotRequired[str]


class BackupKdfRecord(TypedDict):
    """Password derivation metadata for encrypted backups."""

    name: str
    iterations: int
    salt: str


class BackupCipherRecord(TypedDict):
    """Cipher metadata for encrypted backups."""

    name: str
    nonce: str
    ciphertext: str


class EncryptedBackupRecord(TypedDict):
    """Encrypted backup file payload."""

    format: str
    kdf: BackupKdfRecord
    cipher: BackupCipherRecord


class BackupPayload(TypedDict):
    """Decrypted backup snapshot."""

    format_version: int
    created_at: int
    username: str
    user: UserRecord
    root_seed: str
    signing_private: str
    iro_id: str | None
    iro_payload: IROPayload | None
    objects: list[BeepObjectRecord]
    rsa_private_pem: NotRequired[str]
    rsa_public_pem: NotRequired[str]


class CommandState(Protocol):
    """Minimal state interface used by command dispatchers."""

    user: str | None
    pubkey: str | None
    mode: Any
    current_chat: str | None
    current_room: str | None

    def enter_chat(self, username: str) -> None:
        """Enter chat mode."""

    def enter_room(self, room_name: str) -> None:
        """Enter room mode."""

    def exit_chat(self) -> None:
        """Exit chat mode."""

    def exit_room(self) -> None:
        """Exit room mode."""

    def exit_profile(self) -> None:
        """Exit profile mode."""


class CommandDispatcher(Protocol):
    """Callable signature for command dispatch functions."""

    def __call__(self, cmd: str, args: str, state: CommandState) -> None:
        """Dispatch a parsed command."""


class ObjectSerializable(Protocol):
    """Protocol for objects that can be converted to stored records."""

    def to_dict(self) -> BeepObjectRecord:
        """Serialize to a stored object record."""
        ...
