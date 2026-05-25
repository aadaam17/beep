"""Dedicated room screen for the Textual Beep app."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from storage.room_service import RoomService
from storage.session import load_session


class RoomScreen(Screen[None]):
    """Room thread screen with an inline composer."""

    BINDINGS = [
        Binding("r", "refresh_room", "Refresh"),
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    def __init__(self, room_name: str) -> None:
        super().__init__()
        self.room_name = room_name
        self.room_service = RoomService()

    def compose(self) -> ComposeResult:
        """Render the room view."""

        yield Label(f"Room {self.room_name}", id="room-screen-title")
        yield Static("", id="room-screen-body")
        yield Input(
            placeholder="Type a room message and press Enter",
            id="room-screen-input",
        )

    def on_mount(self) -> None:
        """Load initial room details."""

        self._refresh_room_body()
        self.set_interval(1.0, self._refresh_room_body)

    def action_refresh_room(self) -> None:
        """Refresh visible room state/messages."""

        self._refresh_room_body()

    def action_back(self) -> None:
        """Return to the previous screen."""

        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send a room message from the inline composer."""

        if event.input.id != "room-screen-input":
            return

        content = event.value.strip()
        if not content:
            return

        session = load_session()
        if session is None:
            self.query_one("#room-screen-body", Static).update(
                "Log in to send room messages."
            )
            return

        try:
            self.room_service.say(
                self.room_name,
                session["username"],
                content,
            )
        except Exception as exc:
            self.query_one("#room-screen-body", Static).update(
                f"Could not send room message: {exc}"
            )
            return

        event.input.value = ""
        self._refresh_room_body()

    def _refresh_room_body(self) -> None:
        """Render the current room transcript and metadata."""

        body = self.query_one("#room-screen-body", Static)
        room_state = self.room_service.build_room_state(self.room_name)
        if room_state is None:
            body.update("This room is not available.")
            return

        lines = [
            f"Owner: {room_state['owner']}",
            f"Type: {room_state['type']}",
            f"Members: {len(room_state['members'])}",
        ]
        expires_at = room_state.get("expires_at")
        if isinstance(expires_at, (int, float)):
            remaining = max(int(expires_at - time.time()), 0)
            lines.append(f"Expires in: {_format_remaining(remaining)}")
        lines.append("")

        session = load_session()
        if session is None:
            lines.append("Log in to read room messages.")
            body.update("\n".join(lines))
            return

        messages, _ = self.room_service.read_messages(
            self.room_name,
            session["username"],
            start=0,
            limit=100000,
        )
        if not messages:
            lines.extend(
                [
                    "No visible room messages yet.",
                    "",
                    "Use the composer below to send the first visible room message.",
                ]
            )
            body.update("\n".join(lines))
            return

        lines.extend(
            f"{message['sender']}\n{message['content']}" for message in messages
        )
        body.update("\n\n".join(lines))


def _format_remaining(seconds: int) -> str:
    """Render a compact room expiry countdown."""

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
