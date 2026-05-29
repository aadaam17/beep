"""Application runtime state for the interactive CLI."""

from __future__ import annotations

from enum import Enum, auto
from typing import Literal

from core.types import SessionRecord
from storage.session import load_session

SessionRefreshStatus = Literal["changed", "same", "cleared", "none"]
FeedKind = Literal["global", "followed"]


class Mode(Enum):
    """Interactive CLI modes."""

    GLOBAL_FYP = auto()
    FOLLOWED_FYP = auto()
    CHAT = auto()
    ROOM = auto()
    PROFILE = auto()


class AppState:
    """Mutable runtime state shared by the CLI command loop."""

    mode: Mode
    fyp_index: int
    fyp_type: FeedKind
    current_chat: str | None
    current_room: str | None
    hold: bool
    peers: list[str]
    user: str | None
    pubkey: str | None

    def __init__(self) -> None:
        self.mode = Mode.GLOBAL_FYP
        self.fyp_index = 0
        self.fyp_type = "global"
        self.current_chat = None
        self.current_room = None
        self.hold = False
        self.peers = []
        self.user = None
        self.pubkey = None
        self.apply_session(load_session())

    def apply_session(self, session: SessionRecord | None) -> None:
        """Apply a persisted session record to the live state."""

        self.user = session["username"] if session else None
        self.pubkey = session["pubkey"] if session else None

    def refresh_session(self) -> SessionRefreshStatus:
        """Reload session state and report what changed."""

        session = load_session()

        if session:
            if self.user != session["username"] or self.pubkey != session["pubkey"]:
                self.apply_session(session)
                return "changed"
            return "same"

        if self.user or self.pubkey:
            self.apply_session(None)
            self.exit_chat()
            self.exit_room()
            self.exit_profile()
            return "cleared"

        return "none"

    def switch_fyp(self, feed_type: FeedKind) -> None:
        """Switch between the supported feed views."""

        if feed_type not in {"global", "followed"}:
            raise ValueError("Invalid FYP type")

        self.fyp_type = feed_type
        self.mode = (
            Mode.GLOBAL_FYP if feed_type == "global" else Mode.FOLLOWED_FYP
        )

    def enter_chat(self, username: str) -> None:
        """Enter a direct chat context."""

        self.mode = Mode.CHAT
        self.current_chat = username

    def exit_chat(self) -> None:
        """Leave the current chat context."""

        self.mode = Mode.GLOBAL_FYP
        self.current_chat = None

    def enter_room(self, room_name: str) -> None:
        """Enter a room context."""

        self.mode = Mode.ROOM
        self.current_room = room_name

    def exit_room(self) -> None:
        """Leave the current room context."""

        self.mode = Mode.GLOBAL_FYP
        self.current_room = None

    def enter_profile(self) -> None:
        """Enter profile view mode."""

        self.mode = Mode.PROFILE

    def exit_profile(self) -> None:
        """Leave profile view mode."""

        self.mode = Mode.GLOBAL_FYP

    def toggle_hold(self) -> bool:
        """Toggle feed paging hold state."""

        self.hold = not self.hold
        return self.hold
