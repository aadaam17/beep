"""Dedicated post/thread screen for the Textual Beep app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static

from core.create import create_post
from core.identity import build_identity_handle, resolve_username
from core.thread_view import relative_time
from core.types import BeepObjectRecord
from storage.objects import get_object, query_objects
from storage.session import load_session


def _meta_string(obj: BeepObjectRecord, key: str) -> str | None:
    """Extract a non-empty string metadata value."""

    value = obj["meta"].get(key)
    return value if isinstance(value, str) and value else None


def _children_by_parent() -> dict[str, list[BeepObjectRecord]]:
    """Build an in-memory nested comment map."""

    children: dict[str, list[BeepObjectRecord]] = {}
    for obj in query_objects(obj_type="comment"):
        parent_id = _meta_string(obj, "parent_id")
        if parent_id is None:
            continue
        children.setdefault(parent_id, []).append(obj)

    for siblings in children.values():
        siblings.sort(key=lambda item: item["timestamp"])
    return children


def _short_id(value: str | None) -> str:
    """Render a compact object ID for UI summaries."""

    if not value:
        return "(none)"
    if len(value) <= 16:
        return value
    return f"{value[:12]}..."


def _truncate_text(value: str, *, limit: int = 90) -> str:
    """Render a compact single-line preview."""

    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _absolute_date(timestamp: float) -> str:
    """Render absolute dates the same way command mode does."""

    try:
        return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError):
        return "??.??.????"


def _render_thread(root: BeepObjectRecord, *, indent: int = 0) -> list[str]:
    """Render a post/comment subtree into text lines."""

    author = resolve_username(root["author"])
    prefix = "    " * indent
    lines = [
        f"{prefix}@{author} - {relative_time(root['timestamp']) or 'just now'}",
        f"{prefix}{root['content']}",
    ]

    object_id = root["id"]
    for child in _children_by_parent().get(object_id, []):
        lines.append("")
        lines.extend(_render_thread(child, indent=indent + 1))

    return lines


@dataclass(frozen=True)
class ThreadNode:
    """A selectable node inside a rendered post thread."""

    object_id: str
    label: str
    details: list[str]


class PostScreen(Screen[None]):
    """Dedicated post detail/thread screen."""

    DEFAULT_CSS = """
    #post-screen-title, #post-screen-status, #post-screen-hint, #post-screen-detail {
        padding: 1 2;
    }

    #post-screen-status, #post-screen-hint {
        color: $text-muted;
    }

    #post-screen-thread {
        height: 1fr;
        border: round $panel;
        margin: 0 2;
    }

    #post-screen-detail, #post-screen-input {
        height: 4;
        border: round $panel;
        margin: 1 2 0 2;
    }
    """

    BINDINGS = [
        Binding("c", "compose_comment", "Comment"),
        Binding("s", "share_post", "Share"),
        Binding("q", "compose_quote", "Quote"),
        Binding("r", "refresh_post", "Refresh"),
        Binding("b", "back", "Back"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, object_id: str) -> None:
        super().__init__()
        self.object_id = object_id
        self.compose_mode: Literal["comment", "quote"] | None = None
        self.status_message = ""
        self._thread_nodes: list[ThreadNode] = []

    def compose(self) -> ComposeResult:
        """Render the post/thread view."""

        yield Label("Post", id="post-screen-title")
        yield Static("", id="post-screen-status")
        yield Static(
            "Arrow keys move through the thread. c reply, q quote, s share, b back.",
            id="post-screen-hint",
        )
        with Vertical():
            yield ListView(id="post-screen-thread")
            yield Static("", id="post-screen-detail")
            yield Input(
            placeholder="Press c to comment, q to quote, or s to share.",
            id="post-screen-input",
            disabled=True,
            )

    def on_mount(self) -> None:
        """Load the initial post/thread view."""

        self._refresh_post_body()
        self._show_compose_mode(False)

    def action_back(self) -> None:
        """Return to the previous screen."""

        self.app.pop_screen()

    def action_refresh_post(self) -> None:
        """Refresh the currently visible post/thread state."""

        self._refresh_post_body()

    def action_compose_comment(self) -> None:
        """Enable inline reply composition for the selected thread node."""

        target = self._selected_thread_node()
        if target is None:
            return
        self.compose_mode = "comment"
        self._set_input_state(
            enabled=True,
            placeholder=f"Reply to the selected item ({target.object_id[:12]}...) and press Enter",
        )
        self.query_one("#post-screen-input", Input).focus()

    def action_compose_quote(self) -> None:
        """Enable inline quote composition for the selected thread node."""

        target = self._selected_thread_node()
        if target is None:
            return
        self.compose_mode = "quote"
        self._set_input_state(
            enabled=True,
            placeholder=f"Quote the selected item ({target.object_id[:12]}...) and press Enter",
        )
        self.query_one("#post-screen-input", Input).focus()

    def action_share_post(self) -> None:
        """Create a share object for the selected thread node."""

        session = load_session()
        if session is None:
            self.status_message = "Log in to share posts."
            self._refresh_post_body()
            return

        target = self._selected_thread_node()
        if target is None:
            return

        obj = get_object(target.object_id)
        if obj is None:
            self.status_message = "This post is no longer available."
            self._refresh_post_body()
            return

        try:
            shared_id = create_post(
                session["pubkey"],
                obj["content"],
                post_type="share",
                shared_from=target.object_id,
            )
        except Exception as exc:
            self.status_message = f"Could not share post: {exc}"
            self._refresh_post_body()
            return

        self.status_message = f"Shared selected item as {shared_id}."
        self._refresh_post_body()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Create a nested reply or quote from the inline composer."""

        if event.input.id != "post-screen-input":
            return

        content = event.value.strip()
        if not content or self.compose_mode is None:
            return

        session = load_session()
        if session is None:
            self.status_message = "Log in to interact with posts."
            self._refresh_post_body()
            return
        target = self._selected_thread_node()
        if target is None:
            return

        try:
            if self.compose_mode == "comment":
                created_id = create_post(
                    session["pubkey"],
                    content,
                    post_type="comment",
                    parent_id=target.object_id,
                )
                self.status_message = f"Reply posted as {created_id}."
            else:
                created_id = create_post(
                    session["pubkey"],
                    content,
                    post_type="quote",
                    shared_from=target.object_id,
                    quote=True,
                )
                self.status_message = f"Quote posted as {created_id}."
        except Exception as exc:
            action_name = "comment" if self.compose_mode == "comment" else "quote"
            self.status_message = f"Could not create {action_name}: {exc}"
            self._refresh_post_body()
            return

        event.input.value = ""
        self.compose_mode = None
        self._set_input_state(
            enabled=False,
            placeholder="Press c to comment, q to quote, or s to share.",
        )
        self._refresh_post_body()

    def _refresh_post_body(self) -> None:
        """Render the thread list and the selected node detail."""

        title = self.query_one("#post-screen-title", Label)
        status = self.query_one("#post-screen-status", Static)
        detail = self.query_one("#post-screen-detail", Static)
        list_view = self.query_one("#post-screen-thread", ListView)
        obj = get_object(self.object_id)
        if obj is None:
            title.update("Post not found")
            status.update("The selected object is no longer available.")
            detail.update("The selected object is no longer available.")
            self._set_input_state(
                enabled=False,
                placeholder="This post is no longer available.",
            )
            return

        author = resolve_username(obj["author"])
        timestamp = relative_time(obj["timestamp"]) or "just now"
        title.update(f"@{author} - {timestamp}")
        status.update(
            self.status_message or "Select a post or comment, then press c to reply to that exact item."
        )

        previous_selection = self._selected_thread_node()
        self._thread_nodes = []
        list_view.clear()

        for index, node in enumerate(self._flatten_thread(obj)):
            self._thread_nodes.append(node)
            list_view.append(ListItem(Label(node.label)))
            if previous_selection is not None and previous_selection.object_id == node.object_id:
                list_view.index = index

        if not self._thread_nodes:
            detail.update("No thread items are available.")
            return

        if list_view.highlighted_child is None:
            list_view.index = 0

        selected = self._selected_thread_node()
        if selected is not None:
            detail.update("\n".join(selected.details))
        else:
            detail.update("\n".join(self._thread_nodes[0].details))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Render the selected post or comment detail."""

        if event.list_view.id != "post-screen-thread":
            return
        item = event.item
        if item is None:
            return
        node = self._selected_thread_node()
        if node is None:
            return
        self.query_one("#post-screen-detail", Static).update("\n".join(node.details))

    def _set_input_state(self, *, enabled: bool, placeholder: str) -> None:
        """Enable or disable the inline social composer."""

        composer = self.query_one("#post-screen-input", Input)
        composer.disabled = not enabled
        composer.placeholder = placeholder
        if not enabled:
            composer.value = ""
        self._show_compose_mode(enabled)

    def _selected_thread_node(self) -> ThreadNode | None:
        """Return the currently selected thread node."""

        list_view = self.query_one("#post-screen-thread", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._thread_nodes):
            return None
        return self._thread_nodes[index]

    def _show_compose_mode(self, enabled: bool) -> None:
        """Show either the compact detail view or the inline composer."""

        detail = self.query_one("#post-screen-detail", Static)
        composer = self.query_one("#post-screen-input", Input)
        detail.display = not enabled
        composer.display = enabled

    def _flatten_thread(
        self,
        root: BeepObjectRecord,
        *,
        indent: int = 0,
    ) -> list[ThreadNode]:
        """Flatten a nested thread into selectable UI nodes."""

        author = resolve_username(root["author"])
        handle = build_identity_handle(author, root["author"])
        rel = relative_time(root["timestamp"]) or "just now"
        date = _absolute_date(root["timestamp"])
        prefix = "    " * indent
        details = [
            f"Selected: @{author} - {root['type']} - {_short_id(root['id'])}",
            f"Handle: {handle}",
        ]
        if root["type"] == "comment":
            label_lines = [f"{prefix}: [{rel}] [{author}] - : {root['content']}"]
        elif root["type"] == "quote":
            label_lines = [f"{prefix}Quoted [{date} | {rel}] [{author}] - : {root['content']}"]
        elif root["type"] == "share":
            label_lines = [f"{prefix}Shared [{date} | {rel}] [{author}]"]
        else:
            label_lines = [f"{prefix}:: [{date} | {rel}] [{author}] - : {root['content']}"]

        parent_id = _meta_string(root, "parent_id")
        if parent_id is not None:
            details.append(f"Replying to: {_short_id(parent_id)}")
        shared_from = _meta_string(root, "shared_from")
        if shared_from is not None:
            source = get_object(shared_from)
            source_author = (
                resolve_username(source["author"]) if source is not None else "(unknown)"
            )
            source_content = (
                source["content"] if source is not None else "Original post unavailable."
            )
            relationship = "Quoted post" if root["type"] == "quote" else "Shared post"
            source_rel = (
                relative_time(source["timestamp"]) or "just now"
                if source is not None
                else "unknown"
            )
            label_lines.append(f"{prefix}    : [{source_rel}] [{source_author}] - : {source_content}")
            details.append(f"{relationship}: @{source_author} - {_short_id(shared_from)}")
            details.append(source_content)
        details.extend(
            [
                f"Preview: {_truncate_text(root['content'])}",
            ]
        )

        nodes = [ThreadNode(object_id=root["id"], label="\n".join(label_lines), details=details)]
        for child in _children_by_parent().get(root["id"], []):
            nodes.extend(self._flatten_thread(child, indent=indent + 1))
        return nodes
