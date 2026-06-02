"""Dedicated room screen for the Textual Beep app."""

from __future__ import annotations

import time
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static

from core.identity import resolve_username
from storage.room_service import RoomService
from storage.session import load_session


@dataclass(frozen=True)
class MemberCard:
    """Selectable member row shown in the room admin panel."""

    username: str
    pubkey: str
    tags: list[str]
    mute_detail: str | None = None


class RoomScreen(Screen[None]):
    """Room thread screen with members, invites, and moderation controls."""

    DEFAULT_CSS = """
    RoomScreen {
        layout: vertical;
    }

    #room-screen-title {
        padding: 0 1;
        text-style: bold;
    }

    #room-screen-layout {
        height: 1fr;
    }

    #room-screen-main {
        width: 1fr;
        min-width: 60;
        padding: 0 1 1 1;
    }

    #room-screen-side {
        width: 38;
        min-width: 34;
        border-left: solid $panel;
        padding: 0 1 1 1;
    }

    #room-screen-body {
        height: 1fr;
        overflow-y: auto;
        border: round $panel;
        padding: 1;
    }

    #room-screen-input {
        margin-top: 1;
    }

    #room-side-title {
        padding-top: 1;
        text-style: bold;
    }

    #room-summary {
        border: round $panel;
        padding: 0 1;
        margin-top: 0;
    }

    #room-admin-status {
        border: round $panel;
        padding: 1;
        margin-top: 1;
    }

    #room-members-list {
        height: 1fr;
        min-height: 8;
        border: round $panel;
        margin-top: 1;
    }

    #room-admin-input {
        margin-top: 1;
    }

    .muted {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_room", "Refresh"),
        Binding("a", "focus_admin", "Command"),
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    def __init__(self, room_name: str) -> None:
        super().__init__()
        self.room_name = room_name
        self.room_service = RoomService()
        self._member_cards: list[MemberCard] = []
        self._member_snapshot: tuple[tuple[str, tuple[str, ...]], ...] | None = None
        self._selected_member_pubkey: str | None = None
        self._status_message: str = ""

    def compose(self) -> ComposeResult:
        """Render the room view."""

        yield Label(f"Room {self.room_name}", id="room-screen-title")
        with Horizontal(id="room-screen-layout"):
            with Vertical(id="room-screen-main"):
                yield Static("", id="room-screen-body")
                yield Input(
                    placeholder="Type a room message and press Enter",
                    id="room-screen-input",
                )
            with Vertical(id="room-screen-side"):
                yield Label("Members / Admin", id="room-side-title")
                yield Static("", id="room-summary")
                yield ListView(id="room-members-list")
                yield Input(placeholder="Room command", id="room-admin-input")
                yield Static("", id="room-admin-status", classes="muted")

    def on_mount(self) -> None:
        """Load initial room details."""

        self._join_room_if_allowed()
        self._refresh_room_body()
        self.set_interval(1.0, self._refresh_room_body)

    def action_refresh_room(self) -> None:
        """Refresh visible room state/messages."""

        self._refresh_room_body()

    def action_back(self) -> None:
        """Return to the previous screen."""

        self.app.pop_screen()

    def action_focus_admin(self) -> None:
        """Focus the admin command input when available."""

        admin_input = self.query_one("#room-admin-input", Input)
        if admin_input.display:
            admin_input.focus()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update the admin status as member selection changes."""

        if event.list_view.id == "room-members-list":
            index = event.list_view.index
            if index is not None and 0 <= index < len(self._member_cards):
                self._selected_member_pubkey = self._member_cards[index].pubkey
        self._render_admin_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle room message and admin command submissions."""

        if event.input.id == "room-screen-input":
            self._send_room_message(event.value.strip())
            event.input.value = ""
            return

        if event.input.id == "room-admin-input":
            self._run_admin_command(event.value.strip())
            event.input.value = ""

    def _send_room_message(self, content: str) -> None:
        """Send a room message from the inline composer."""

        if not content:
            return

        session = load_session()
        if session is None:
            self._status_message = "Log in to send room messages."
            self._refresh_room_body()
            return

        if not self._join_room_if_allowed():
            self._refresh_room_body()
            return

        try:
            self.room_service.say(self.room_name, session["username"], content)
        except Exception as exc:
            self._status_message = f"Could not send room message: {exc}"
            self._refresh_room_body()
            return

        self._status_message = "Message sent."
        self._refresh_room_body()

    def _join_room_if_allowed(self) -> bool:
        """Join the current room when the active user already has access."""

        session = load_session()
        if session is None:
            return False

        room_state = self.room_service.build_room_state(self.room_name)
        if room_state is None:
            self._status_message = "This room is not available."
            return False

        actor_pubkey = (
            session["pubkey"] if isinstance(session.get("pubkey"), str) else None
        )
        if actor_pubkey is None:
            return False
        if actor_pubkey in room_state["members"]:
            return True
        if actor_pubkey in room_state["banned"]:
            self._status_message = "You are banned from this room."
            return False

        has_access = (
            room_state["type"] == "public"
            or actor_pubkey == room_state["owner_pubkey"]
            or actor_pubkey in room_state["invited"]
        )
        if not has_access:
            self._status_message = "You need an invite before joining this room."
            return False

        try:
            result = self.room_service.join_room(
                self.room_name,
                session["username"],
            )
        except Exception as exc:
            self._status_message = f"Could not join room: {exc}"
            return False

        if result == "joined":
            self._status_message = f"Joined room {self.room_name}."
        return True

    def _invite_user(self, raw_target: str) -> None:
        """Invite a user from the admin panel."""

        target = raw_target.strip()
        if not target:
            return

        session = load_session()
        if session is None:
            self._status_message = "Log in to invite users."
            self._refresh_room_body()
            return

        room_state = self.room_service.build_room_state(self.room_name)
        if room_state is None:
            self._status_message = "This room is not available."
            self._refresh_room_body()
            return

        if room_state["type"] != "private":
            self._status_message = "Invites are only needed for private rooms."
            self._refresh_room_body()
            return

        actor_pubkey = (
            session["pubkey"] if isinstance(session.get("pubkey"), str) else None
        )
        if not self._can_invite(room_state, actor_pubkey):
            self._status_message = "You do not have permission to invite users here."
            self._refresh_room_body()
            return

        try:
            result = self.room_service.invite(
                self.room_name,
                target,
                actor=session["username"],
            )
        except Exception as exc:
            self._status_message = f"Invite failed: {exc}"
            self._refresh_room_body()
            return

        if result == "already_member":
            self._status_message = f"{target} is already in the room."
        elif result == "already_invited":
            self._status_message = f"{target} already has a valid invite."
        else:
            self._status_message = f"Invited {target}."
        self._refresh_room_body()

    def _run_admin_command(self, raw_command: str) -> None:
        """Run a moderation or room-admin command from the side panel."""

        command = raw_command.strip()
        if not command:
            return

        session = load_session()
        if session is None:
            self._status_message = "Log in to use room controls."
            self._refresh_room_body()
            return

        parts = command.split()
        action = parts[0].lower()
        args = parts[1:]
        selected_member = self._selected_member_card()
        room_state = self.room_service.build_room_state(self.room_name)
        actor_pubkey = (
            session["pubkey"] if isinstance(session.get("pubkey"), str) else None
        )

        if room_state is None:
            self._status_message = "This room is not available."
            self._refresh_room_body()
            return

        if action == "dissolve":
            if not self._can_dissolve(room_state, actor_pubkey):
                self._status_message = "Only the room owner can dissolve this room."
                self._refresh_room_body()
                return
            try:
                self.room_service.dissolve_room(self.room_name, session["username"])
            except Exception as exc:
                self._status_message = f"Dissolve failed: {exc}"
                self._refresh_room_body()
                return

            self._status_message = f"Dissolved room {self.room_name}."
            self.app.pop_screen()
            return

        permanent = False
        target = ""
        filtered_args: list[str] = []
        for item in args:
            if item == "--perma":
                permanent = True
                continue
            filtered_args.append(item)

        if action == "invite":
            if not filtered_args:
                self._status_message = "Use: invite <username|handle>."
                self._refresh_room_body()
                return
            self._invite_user(filtered_args[0])
            return

        if filtered_args:
            target = filtered_args[0]
        elif selected_member is not None:
            target = selected_member.username

        if not target:
            self._status_message = "Pick a member or include a username."
            self._refresh_room_body()
            return

        if action in {"mod", "unmod"} and not self._can_manage_mods(
            room_state, actor_pubkey
        ):
            self._status_message = "Only the room owner can manage moderators."
            self._refresh_room_body()
            return

        if action in {"mute", "unmute", "kick"} and not self._can_moderate(
            room_state, actor_pubkey
        ):
            self._status_message = "Only the owner or moderators can manage members."
            self._refresh_room_body()
            return

        try:
            if action == "mod":
                result = self.room_service.room_mod(
                    self.room_name, session["username"], target, promote=True
                )
                self._status_message = (
                    f"{target} is already a moderator."
                    if result == "already_mod"
                    else f"{target} is now a moderator."
                )
            elif action == "unmod":
                result = self.room_service.room_mod(
                    self.room_name, session["username"], target, promote=False
                )
                self._status_message = (
                    f"{target} is not a moderator."
                    if result == "not_mod"
                    else f"{target} removed from moderators."
                )
            elif action == "mute":
                result = self.room_service.room_mute(
                    self.room_name,
                    session["username"],
                    target,
                    permanent=permanent,
                )
                if result == "already_muted":
                    self._status_message = f"{target} is already muted."
                elif permanent:
                    self._status_message = f"{target} muted permanently."
                else:
                    self._status_message = f"{target} muted for 24h."
            elif action == "unmute":
                result = self.room_service.room_unmute(
                    self.room_name, session["username"], target
                )
                self._status_message = (
                    f"{target} is not muted."
                    if result == "not_muted"
                    else f"{target} unmuted."
                )
            elif action == "kick":
                result = self.room_service.room_kick(
                    self.room_name, session["username"], target
                )
                if result == "already_banned":
                    self._status_message = f"{target} is already banned."
                elif result == "not_member":
                    self._status_message = f"{target} is not in the room."
                else:
                    self._status_message = f"{target} kicked and banned."
            else:
                self._status_message = (
                    "Use invite, mod, unmod, mute, unmute, kick, or dissolve."
                )
        except Exception as exc:
            self._status_message = f"Room action failed: {exc}"

        self._refresh_room_body()

    def _selected_member_card(self) -> MemberCard | None:
        """Return the currently selected room member."""

        if not self._member_cards:
            return None

        if self._selected_member_pubkey is not None:
            for card in self._member_cards:
                if card.pubkey == self._selected_member_pubkey:
                    return card

        return self._member_cards[0]

    def _refresh_room_body(self) -> None:
        """Render the current room transcript, membership, and admin state."""

        room_state = self.room_service.build_room_state(self.room_name)
        body = self.query_one("#room-screen-body", Static)
        summary = self.query_one("#room-summary", Static)
        members_list = self.query_one("#room-members-list", ListView)
        admin_input = self.query_one("#room-admin-input", Input)

        if room_state is None:
            body.update("This room is not available.")
            summary.update("Room unavailable.")
            self._member_snapshot = None
            self._selected_member_pubkey = None
            members_list.clear()
            admin_input.display = False
            self.query_one("#room-admin-status", Static).update(
                self._status_message or "The room may have expired or been dissolved."
            )
            return

        session = load_session()
        actor_pubkey = (
            session["pubkey"]
            if session is not None and isinstance(session.get("pubkey"), str)
            else None
        )
        actor_username = (
            session["username"]
            if session is not None and isinstance(session.get("username"), str)
            else None
        )

        self._refresh_summary(room_state, actor_pubkey)
        self._refresh_members(room_state, actor_pubkey)
        self._refresh_messages(room_state, actor_username)

        can_invite = self._can_invite(room_state, actor_pubkey)
        can_moderate = self._can_moderate(room_state, actor_pubkey)
        can_manage_mods = self._can_manage_mods(room_state, actor_pubkey)
        can_dissolve = self._can_dissolve(room_state, actor_pubkey)
        admin_input.display = can_invite or can_moderate or can_dissolve

        if can_manage_mods:
            admin_input.placeholder = "Owner command"
        elif can_moderate:
            admin_input.placeholder = "Moderator command"
        elif can_invite:
            admin_input.placeholder = "Invite command"
        else:
            admin_input.placeholder = "Owner and moderators can manage this room"

        self._render_admin_status(room_state)

    def _refresh_summary(self, room_state: dict[str, object], actor_pubkey: str | None) -> None:
        """Update the room summary block."""

        summary = self.query_one("#room-summary", Static)
        lines = [
            f"Owner: {room_state['owner']}",
            f"Type: {room_state['type']}",
            f"Members: {len(room_state['members'])}",
        ]

        invited_count = len(
            [
                pubkey
                for pubkey in room_state["invited"]
                if pubkey not in room_state["members"]
            ]
        )
        if room_state["type"] == "private":
            lines.append(f"Pending invites: {invited_count}")

        expires_at = room_state.get("expires_at")
        if isinstance(expires_at, (int, float)):
            remaining = max(int(expires_at - time.time()), 0)
            lines.append(f"Expires in: {_format_remaining(remaining)}")

        lines.append(f"Your role: {self._actor_role(room_state, actor_pubkey)}")

        pending_invites = [
            resolve_username(pubkey)
            for pubkey in room_state["invited"]
            if pubkey not in room_state["members"]
        ]
        if pending_invites:
            lines.extend(["", "Invited:", *[f" - {name}" for name in pending_invites]])

        summary.update("\n".join(lines))

    def _refresh_members(
        self, room_state: dict[str, object], actor_pubkey: str | None
    ) -> None:
        """Update the member list while preserving selection."""

        members_list = self.query_one("#room-members-list", ListView)
        previous_selected_pubkey = self._selected_member_pubkey

        member_cards: list[MemberCard] = []
        for pubkey in room_state["members"]:
            tags: list[str] = []
            mute_detail: str | None = None
            if pubkey == room_state["owner_pubkey"]:
                tags.append("owner")
            if pubkey in room_state["moderators"]:
                tags.append("mod")
            if pubkey == actor_pubkey:
                tags.append("you")
            muted_state = room_state["muted"].get(pubkey)
            if muted_state == "perma":
                tags.append("muted")
                mute_detail = "Muted permanently"
            elif isinstance(muted_state, dict) and time.time() < muted_state.get(
                "until", 0.0
            ):
                remaining = max(int(muted_state["until"] - time.time()), 0)
                tags.append("muted")
                mute_detail = f"Muted for {_format_remaining(remaining)} more"
            member_cards.append(
                MemberCard(
                    username=resolve_username(pubkey),
                    pubkey=pubkey,
                    tags=tags,
                    mute_detail=mute_detail,
                )
            )

        member_cards.sort(
            key=lambda card: (
                "owner" not in card.tags,
                "mod" not in card.tags,
                card.username.lower(),
            )
        )
        snapshot = tuple((card.username, tuple(card.tags)) for card in member_cards)
        self._member_cards = member_cards

        if snapshot == self._member_snapshot:
            return
        self._member_snapshot = snapshot

        members_list.clear()
        restored_index = 0
        for card in self._member_cards:
            suffix = f" [{' | '.join(card.tags)}]" if card.tags else ""
            if previous_selected_pubkey == card.pubkey:
                restored_index = len(members_list.children)
            members_list.append(ListItem(Label(f"{card.username}{suffix}")))

        if self._member_cards:
            members_list.index = min(restored_index, len(self._member_cards) - 1)
            if 0 <= members_list.index < len(self._member_cards):
                self._selected_member_pubkey = self._member_cards[members_list.index].pubkey

    def _refresh_messages(
        self, room_state: dict[str, object], actor_username: str | None
    ) -> None:
        """Update the transcript area for the current actor."""

        body = self.query_one("#room-screen-body", Static)
        lines = []

        if actor_username is None:
            lines.extend(
                [
                    "Log in to read room messages.",
                    "",
                    "The room summary and membership view remain available.",
                ]
            )
            body.update("\n".join(lines))
            return

        messages, _ = self.room_service.read_messages(
            self.room_name,
            actor_username,
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

        for message in messages:
            timestamp = time.strftime("%H:%M", time.localtime(message["timestamp"]))
            lines.append(f"[{timestamp}] {message['sender']}: {message['content']}")

        body.update("\n".join(lines))

    def _render_admin_status(self, room_state: dict[str, object] | None = None) -> None:
        """Render helper text or the latest room-control status."""

        status = self.query_one("#room-admin-status", Static)
        if self._status_message:
            status.update(self._status_message)
            return

        room_state = room_state or self.room_service.build_room_state(self.room_name)
        session = load_session()
        actor_pubkey = (
            session["pubkey"]
            if session is not None and isinstance(session.get("pubkey"), str)
            else None
        )
        member = self._selected_member_card()
        if member is None:
            if room_state is not None and self._can_invite(room_state, actor_pubkey):
                status.update("Select a member to inspect, or run `invite <user>` above.")
            else:
                status.update("Select a member to inspect.")
            return

        lines = [f"Selected: {member.username}"]
        if member.tags:
            lines.append(f"Flags: {', '.join(member.tags)}")
        if member.mute_detail:
            lines.append(member.mute_detail)

        can_manage_mods = (
            room_state is not None and self._can_manage_mods(room_state, actor_pubkey)
        )
        can_moderate = room_state is not None and self._can_moderate(
            room_state, actor_pubkey
        )
        can_invite = room_state is not None and self._can_invite(
            room_state, actor_pubkey
        )

        if can_manage_mods:
            owner_command = (
                "Commands: mod <user> | unmod <user> | mute <user> --perma | "
                "unmute <user> | kick <user> | dissolve"
            )
            if can_invite:
                owner_command = (
                    "Commands: invite <user> | mod <user> | unmod <user> | "
                    "mute <user> --perma | unmute <user> | kick <user> | dissolve"
                )
            lines.extend(
                [
                    "",
                    owner_command,
                ]
            )
        elif can_moderate:
            moderator_command = (
                "Commands: invite <user> | mute <user> --perma | unmute <user> | kick <user>"
                if can_invite
                else "Commands: mute <user> --perma | unmute <user> | kick <user>"
            )
            lines.extend(
                [
                    "",
                    moderator_command,
                ]
            )
        elif can_invite:
            lines.extend(["", "Command: invite <user>"])
        else:
            lines.extend(
                ["", "You can read members here. Owner or moderators manage room actions."]
            )

        status.update("\n".join(lines))

    def _can_moderate(
        self, room_state: dict[str, object], actor_pubkey: str | None
    ) -> bool:
        """Return whether the current actor can use moderation actions."""

        if actor_pubkey is None:
            return False
        return (
            actor_pubkey == room_state["owner_pubkey"]
            or actor_pubkey in room_state["moderators"]
        )

    def _actor_role(
        self, room_state: dict[str, object], actor_pubkey: str | None
    ) -> str:
        """Return the actor's effective role in the current room."""

        if actor_pubkey is None:
            return "guest"
        if actor_pubkey == room_state["owner_pubkey"]:
            return "owner"
        if actor_pubkey in room_state["moderators"]:
            return "moderator"
        if actor_pubkey in room_state["members"]:
            return "member"
        return "guest"

    def _can_invite(
        self, room_state: dict[str, object], actor_pubkey: str | None
    ) -> bool:
        """Return whether the actor can invite users into the room."""

        return (
            actor_pubkey is not None
            and actor_pubkey in room_state["members"]
            and room_state["type"] == "private"
        )

    def _can_manage_mods(
        self, room_state: dict[str, object], actor_pubkey: str | None
    ) -> bool:
        """Return whether the actor can promote or demote moderators."""

        return actor_pubkey is not None and actor_pubkey == room_state["owner_pubkey"]

    def _can_dissolve(
        self, room_state: dict[str, object], actor_pubkey: str | None
    ) -> bool:
        """Return whether the actor can dissolve the room."""

        return self._can_manage_mods(room_state, actor_pubkey)


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
