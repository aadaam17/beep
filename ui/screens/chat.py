"""Dedicated chat screen for the Textual Beep app."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Input, Label, Static

from core.thread_view import relative_time
from storage.chat_service import ChatService
from storage.session import load_session


class ChatScreen(Screen[None]):
    """Direct chat thread screen with an inline composer."""

    DEFAULT_CSS = """
    #chat-screen-title, #chat-screen-status, #chat-screen-body {
        padding: 1 2;
    }

    #chat-screen-status {
        color: $text-muted;
    }

    #chat-screen-body {
        height: 1fr;
        border: round $panel;
    }

    #chat-screen-input {
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_chat", "Refresh"),
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    def __init__(self, peer_username: str) -> None:
        super().__init__()
        self.peer_username = peer_username
        self.chat_service = ChatService()
        self._poll_timer: Timer | None = None
        self._last_signature: tuple[tuple[str, float, str], ...] = ()
        self._status_message = "Live chat updates are on."

    def compose(self) -> ComposeResult:
        """Render the chat thread view."""

        yield Label(f"Chat with {self.peer_username}", id="chat-screen-title")
        yield Static("", id="chat-screen-status")
        yield Static("", id="chat-screen-body")
        yield Input(
            placeholder="Type a message and press Enter",
            id="chat-screen-input",
        )

    def on_mount(self) -> None:
        """Load the initial chat transcript."""

        self._refresh_chat_body()
        self._poll_timer = self.set_interval(2.0, self._refresh_chat_body)
        self.query_one("#chat-screen-input", Input).focus()

    def on_unmount(self) -> None:
        """Stop background polling when the screen closes."""

        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None

    def action_refresh_chat(self) -> None:
        """Refresh visible chat messages."""

        self._status_message = "Chat refreshed."
        self._refresh_chat_body()

    def action_back(self) -> None:
        """Return to the previous screen."""

        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send a direct message from the inline composer."""

        if event.input.id != "chat-screen-input":
            return

        content = event.value.strip()
        if not content:
            return

        session = load_session()
        if session is None:
            self._status_message = "Log in to send direct messages."
            self._refresh_chat_body()
            return

        try:
            self.chat_service.chat_say(
                self.peer_username,
                session["username"],
                content,
            )
        except Exception as exc:
            self._status_message = f"Could not send message: {exc}"
            self._refresh_chat_body()
            return

        event.input.value = ""
        self._status_message = "Message sent."
        self._refresh_chat_body()

    def _refresh_chat_body(self) -> None:
        """Render the current chat transcript."""

        session = load_session()
        body = self.query_one("#chat-screen-body", Static)
        status = self.query_one("#chat-screen-status", Static)
        if session is None:
            status.update("Session required")
            body.update("Log in to read direct messages.")
            return

        messages, _ = self.chat_service.chat_read_messages(
            self.peer_username,
            session["username"],
            start=0,
            limit=100000,
        )
        signature = tuple(
            (message["sender"], message["timestamp"], message["content"])
            for message in messages
        )
        status.update(
            f"{len(messages)} message(s) with @{self.peer_username} | {self._status_message}"
        )
        if not messages:
            body.update(
                "\n".join(
                    [
                        f"No messages with {self.peer_username} yet.",
                        "",
                        "Use the composer below to send the first message.",
                    ]
                )
            )
            self._last_signature = ()
            return

        if signature == self._last_signature:
            return

        body.update("\n\n".join(self._format_message(message) for message in messages))
        self._last_signature = signature

    def _format_message(self, message: dict[str, object]) -> str:
        """Render one chat message in a cleaner conversation format."""

        sender = str(message["sender"])
        content = str(message["content"])
        timestamp = message.get("timestamp")
        if isinstance(timestamp, (int, float)):
            clock = datetime.fromtimestamp(timestamp).strftime("%H:%M")
            rel = relative_time(float(timestamp)) or "just now"
            header = f"{sender} [{clock} | {rel}]"
        else:
            header = sender

        return "\n".join(
            [
                header,
                content,
            ]
        )
