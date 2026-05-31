"""Home/feed screen for the Textual Beep app."""

from __future__ import annotations

import io
import textwrap
from datetime import datetime
from dataclasses import dataclass
from contextlib import redirect_stdout
from types import SimpleNamespace

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Checkbox, Input, Label, ListItem, ListView, Static

from commands.room import EPHEMERAL_TTL_SECONDS
from core.create import create_post
from core.feed import get_all_posts, get_followed_posts
from core.identity import build_identity_handle, find_identity_matches, resolve_username
from core.thread_view import relative_time
from core.types import BeepObjectRecord
from network.node_manager import load_node_runtime
from network.peers import load_peers
from network.reachability import probe_endpoint
from state import FeedKind
from storage.network_policy import load_network_policy, order_network_targets
from storage.chat_service import ChatService
from storage.room_service import RoomService
from storage.objects import get_object, query_objects
from storage.profile import (
    follow,
    get_effective_followers,
    get_effective_following,
    get_known_users,
    get_user,
    is_following,
    unfollow,
)
from storage.relay import load_relays
from storage.session import clear_session, load_session
from commands.connect import dispatch as connect_dispatch
from commands.network import dispatch as network_dispatch
from commands.relay import dispatch as relay_dispatch
from commands.storage import dispatch as storage_dispatch
from commands.sync import SyncCommand
from ui.screens.chat import ChatScreen
from ui.screens.post import PostScreen
from ui.screens.room import RoomScreen
from ui.widgets.sidebar import Sidebar


@dataclass(frozen=True)
class FeedCard:
    """Lightweight feed item model for Textual rendering."""

    object_id: str
    author_name: str
    author_handle: str
    kind: str
    relative_timestamp: str
    content: str
    headline: str
    preview: str
    context_lines: list[str]
    display_lines: list[str]


@dataclass(frozen=True)
class ChatCard:
    """Lightweight direct chat preview for the home shell."""

    peer_username: str
    preview: str
    status: str
    messages: list[str]


@dataclass(frozen=True)
class RoomCard:
    """Lightweight room preview for the home shell."""

    room_name: str
    preview: str
    status: str
    details: list[str]


@dataclass(frozen=True)
class ProfileCard:
    """Profile panel item for the home shell."""

    item_id: str
    title: str
    preview: str
    details: list[str]
    target_pubkey: str | None = None
    target_username: str | None = None
    followable: bool = False


@dataclass(frozen=True)
class NetworkCard:
    """Network panel item for the home shell."""

    item_id: str
    title: str
    preview: str
    details: list[str]
    console_command: str | None = None
    compose_seed: str | None = None


@dataclass(frozen=True)
class SearchCard:
    """Known-user search result model for the interactive shell."""

    title: str
    preview: str
    details: list[str]
    target_pubkey: str
    target_username: str
    handle: str


def _meta_string(obj: BeepObjectRecord, key: str) -> str | None:
    """Extract a string metadata value from an object."""

    value = obj["meta"].get(key)
    return value if isinstance(value, str) and value else None


def _truncate_text(content: str, *, limit: int = 90) -> str:
    """Render a compact single-line preview for list cards."""

    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _absolute_date(timestamp: float) -> str:
    """Render the command-mode absolute date format."""

    try:
        return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError):
        return "??.??.????"


def _preview_lines(content: str, *, width: int = 56, max_lines: int = 3) -> list[str]:
    """Wrap content into a compact multi-line preview."""

    normalized = " ".join(content.split())
    if not normalized:
        return ["(empty)"]

    wrapped = textwrap.wrap(normalized, width=width) or [normalized]
    if len(wrapped) <= max_lines:
        return wrapped

    trimmed = wrapped[:max_lines]
    if len(trimmed[-1]) >= width - 3:
        trimmed[-1] = f"{trimmed[-1][: width - 3]}..."
    else:
        trimmed[-1] = f"{trimmed[-1]}..."
    return trimmed


def _source_context(post: BeepObjectRecord) -> tuple[str, str, str]:
    """Resolve the referenced object for shares and quotes."""

    shared_from = _meta_string(post, "shared_from")
    source = get_object(shared_from) if shared_from is not None else None
    if source is None:
        return "(unknown)", "(unknown)", "Original post unavailable."

    source_author = resolve_username(source["author"])
    source_id = source.get("id") or shared_from or "(unknown)"
    return source_author, source_id, source["content"]


def _comment_children_by_parent() -> dict[str, list[BeepObjectRecord]]:
    """Build a nested comment lookup map for feed rendering."""

    children: dict[str, list[BeepObjectRecord]] = {}
    for obj in query_objects(obj_type="comment"):
        parent_id = _meta_string(obj, "parent_id")
        if parent_id is None:
            continue
        children.setdefault(parent_id, []).append(obj)

    for siblings in children.values():
        siblings.sort(key=lambda item: item["timestamp"])
    return children


def _format_comment_line(obj: BeepObjectRecord, *, indent: int = 1) -> str:
    """Render a comment-style line matching command mode."""

    author = resolve_username(obj["author"])
    prefix = "    " * indent
    rel = relative_time(obj["timestamp"]) or "just now"
    return f"{prefix}: [{rel}] [{author}] - : {obj['content']}"


def _render_comment_tree(
    parent_id: str,
    children: dict[str, list[BeepObjectRecord]],
    *,
    indent: int = 1,
) -> list[str]:
    """Render nested comment descendants for a feed item."""

    lines: list[str] = []
    for child in children.get(parent_id, []):
        lines.append(_format_comment_line(child, indent=indent))
        child_id = child.get("id")
        if child_id:
            lines.extend(_render_comment_tree(child_id, children, indent=indent + 1))
    return lines


def _build_feed_display_lines(
    post: BeepObjectRecord,
    children: dict[str, list[BeepObjectRecord]],
) -> list[str]:
    """Render a feed item using the command-mode thread style."""

    author = resolve_username(post["author"])
    rel = relative_time(post["timestamp"]) or "just now"
    date = _absolute_date(post["timestamp"])
    kind = post["type"]

    if kind == "quote":
        lines = [f"Quoted [{date} | {rel}] [{author}] - : {post['content']}"]
        shared_from = _meta_string(post, "shared_from")
        source = get_object(shared_from) if shared_from is not None else None
        if source is not None:
            lines.append(_format_comment_line(source, indent=1))
    elif kind == "share":
        lines = [f"Shared [{date} | {rel}] [{author}]"]
        shared_from = _meta_string(post, "shared_from")
        source = get_object(shared_from) if shared_from is not None else None
        if source is not None:
            lines.append(_format_comment_line(source, indent=1))
    else:
        lines = [f":: [{date} | {rel}] [{author}] - : {post['content']}"]

    post_id = post.get("id")
    if post_id:
        lines.extend(_render_comment_tree(post_id, children, indent=1))
    return lines


def _build_feed_presentation(post: BeepObjectRecord) -> tuple[str, str, list[str]]:
    """Build timeline-friendly display text for feed objects."""

    kind = post["type"]
    content = post["content"]
    if kind == "post":
        return (
            "Post",
            _truncate_text(content),
            [
                f"Type: {kind}",
                "",
                content,
            ],
        )

    source_author, source_id, source_excerpt = _source_context(post)

    if kind == "share":
        return (
            f"Shared @{source_author}",
            _truncate_text(source_excerpt),
            [
                "Type: share",
                f"Original author: @{source_author}",
                f"Original object: {source_id}",
                "",
                "Shared post:",
                *[f"> {line}" for line in _preview_lines(source_excerpt, max_lines=4)],
            ],
        )

    return (
        f"Quoted @{source_author}",
        _truncate_text(source_excerpt),
        [
            "Type: quote",
            f"Original author: @{source_author}",
            f"Original object: {source_id}",
            "",
            "Your note:",
            *(_preview_lines(content, max_lines=3)),
            "",
            "Quoted post:",
            *[f"> {line}" for line in _preview_lines(source_excerpt, max_lines=4)],
        ],
    )


def _load_feed_cards(feed_type: FeedKind) -> list[FeedCard]:
    """Load the home timeline using the existing storage/feed backend."""

    session = load_session()
    posts: list[BeepObjectRecord]

    if feed_type == "followed" and session is not None:
        following = get_effective_following(session["pubkey"])
        posts = get_followed_posts(following)
    else:
        posts = get_all_posts()

    children = _comment_children_by_parent()
    cards: list[FeedCard] = []
    for post in posts:
        author_name = resolve_username(post["author"])
        headline, preview, context_lines = _build_feed_presentation(post)
        cards.append(
            FeedCard(
                object_id=post["id"],
                author_name=author_name,
                author_handle=build_identity_handle(author_name, post["author"]),
                kind=post["type"],
                relative_timestamp=relative_time(post["timestamp"]) or "just now",
                content=post["content"],
                headline=headline,
                preview=preview,
                context_lines=context_lines,
                display_lines=_build_feed_display_lines(post, children),
            )
        )
    return cards


def _load_chat_cards() -> list[ChatCard]:
    """Load direct chat previews for the current logged-in user."""

    session = load_session()
    if session is None:
        return []

    chat_service = ChatService()
    cards: list[ChatCard] = []
    for peer_username in chat_service.list_chats(session["username"]):
        messages, total = chat_service.chat_read_messages(
            peer_username,
            session["username"],
            start=0,
            limit=100000,
        )
        preview = messages[-1]["content"] if messages else "No messages yet."
        cards.append(
            ChatCard(
                peer_username=peer_username,
                preview=preview,
                status=f"{total} message(s)",
                messages=[
                    f"{message['sender']}: {message['content']}"
                    for message in messages[-10:]
                ],
            )
        )
    return cards


def _load_room_cards() -> list[RoomCard]:
    """Load room previews from the canonical room service."""

    room_service = RoomService()
    session = load_session()
    actor_pubkey = session["pubkey"] if session is not None else None
    cards: list[RoomCard] = []
    for room_name in room_service.list_rooms():
        room_state = room_service.build_room_state(room_name)
        if room_state is None:
            continue
        is_member = actor_pubkey is not None and actor_pubkey in room_state["members"]
        is_owner = actor_pubkey == room_state["owner_pubkey"]
        is_invited = (
            actor_pubkey is not None
            and actor_pubkey in room_state["invited"]
            and not is_member
        )
        if (
            room_state["type"] == "private"
            and not is_owner
            and not is_member
            and not is_invited
        ):
            continue

        if room_state["type"] == "public":
            access_label = "open room"
        elif is_owner:
            access_label = "owner access"
        elif is_member:
            access_label = "member access"
        elif is_invited:
            access_label = "invited"
        else:
            access_label = "invite required"

        preview = f"{access_label} | {len(room_state['members'])} member(s)"
        details = [
            f"Owner: {room_state['owner']}",
            f"Type: {room_state['type']}",
            f"Access: {access_label}",
            f"Members: {len(room_state['members'])}",
        ]
        if session is not None:
            messages, _ = room_service.read_messages(
                room_name,
                session["username"],
                start=0,
                limit=5,
            )
            details.extend(
                [f"{message['sender']}: {message['content']}" for message in messages]
            )
        cards.append(
            RoomCard(
                room_name=room_name,
                preview=preview,
                status=access_label,
                details=details,
            )
        )
    cards.sort(
        key=lambda card: (
            "invited" not in card.status,
            "owner" not in card.status,
            "member" not in card.status,
            card.room_name.lower(),
        )
    )
    return cards


def _load_profile_cards() -> list[ProfileCard]:
    """Load profile information for the logged-in user."""

    session = load_session()
    if session is None:
        return []

    user = get_user(session["username"])
    if user is None:
        return []

    followers = sorted(get_effective_followers(user["pubkey"]))
    following = sorted(get_effective_following(user["pubkey"]))
    authored = query_objects(author=user["pubkey"])
    posts = [obj for obj in authored if obj["type"] == "post"]
    shared = [obj for obj in authored if obj["type"] in {"share", "quote"}]
    cards = [
        ProfileCard(
            item_id="session",
            title="Session",
            preview=f"Signed in as @{user['username']}",
            details=[
                f"Username: {user['username']}",
                f"Handle: {build_identity_handle(user['username'], user['pubkey'])}",
                f"Pubkey: {user['pubkey']}",
            ],
        ),
        ProfileCard(
            item_id="summary",
            title="Summary",
            preview=f"{len(posts)} posts, {len(followers)} followers",
            details=[
                f"Username: {user['username']}",
                f"Handle: {build_identity_handle(user['username'], user['pubkey'])}",
                f"Followers: {len(followers)}",
                f"Following: {len(following)}",
                f"Posts: {len(posts)}",
                f"Shared: {len(shared)}",
            ],
        ),
        ProfileCard(
            item_id="followers",
            title="Followers",
            preview=f"{len(followers)} follower(s)",
            details=[
                "Followers",
                "",
                *(
                    [resolve_username(pubkey) for pubkey in followers]
                    or ["No followers yet."]
                ),
            ],
        ),
        ProfileCard(
            item_id="following",
            title="Following",
            preview=f"{len(following)} following",
            details=[
                "Following",
                "",
                *(
                    [resolve_username(pubkey) for pubkey in following]
                    or ["Not following anyone yet."]
                ),
            ],
        ),
        ProfileCard(
            item_id="posts",
            title="Posts",
            preview=f"{len(posts)} authored post(s)",
            details=[
                "Posts",
                "",
                *([obj["content"] for obj in posts] or ["No posts yet."]),
            ],
        ),
        ProfileCard(
            item_id="shared",
            title="Shared",
            preview=f"{len(shared)} shared/quoted object(s)",
            details=[
                "Shared and quoted",
                "",
                *([obj["content"] for obj in shared] or ["No shared posts yet."]),
            ],
        ),
    ]

    for known_user in get_known_users():
        if known_user["pubkey"] == user["pubkey"]:
            continue
        known_followers = sorted(get_effective_followers(known_user["pubkey"]))
        known_following = sorted(get_effective_following(known_user["pubkey"]))
        followed = is_following(user["pubkey"], known_user["pubkey"])
        handle = build_identity_handle(known_user["username"], known_user["pubkey"])
        cards.append(
            ProfileCard(
                item_id=f"user-{known_user['pubkey']}",
                title=f"@{known_user['username']}",
                preview=(f"{handle} - {'following' if followed else 'not following'}"),
                details=[
                    f"Username: {known_user['username']}",
                    f"Handle: {handle}",
                    f"Followers: {len(known_followers)}",
                    f"Following: {len(known_following)}",
                    f"Status: {'Following' if followed else 'Not following'}",
                    "",
                    "Press `f` to follow or unfollow this user.",
                ],
                target_pubkey=known_user["pubkey"],
                target_username=known_user["username"],
                followable=True,
            )
        )

    return cards


def _load_network_cards() -> list[NetworkCard]:
    """Load network summary information for the shell."""

    policy = load_network_policy()
    peers = load_peers()
    relays = load_relays()
    targets = order_network_targets(peers, relays)
    runtime = load_node_runtime()

    target_details: list[str] = []
    for target in targets:
        kind = "relay" if target in relays else "peer"
        status = probe_endpoint(target)
        target_details.append(f"{target} [{kind}] - {status}")

    runtime_lines = (
        [
            f"URL: {runtime['url']}",
            f"PID: {runtime['pid']}",
            f"User: {runtime['username']}",
        ]
        if runtime is not None
        else ["Local node is not running."]
    )

    return [
        NetworkCard(
            item_id="action-check",
            title="Run check",
            preview="Probe peers and relays now",
            details=[
                "Run a live reachability check for the current network targets.",
                "",
                "Press Enter to execute `network check` now.",
            ],
            console_command="network check",
        ),
        NetworkCard(
            item_id="action-sync",
            title="Sync now",
            preview="Pull objects from current peers",
            details=[
                "Run an immediate object synchronization pass across configured peers.",
                "",
                "Press Enter to execute `sync` now.",
            ],
            console_command="sync",
        ),
        NetworkCard(
            item_id="action-connect",
            title="Show handle",
            preview="Display your Beep handle and discovery posture",
            details=[
                "Show your current handle, pubkey, and discovery status.",
                "",
                "Press Enter to execute `connect` now.",
            ],
            console_command="connect",
        ),
        NetworkCard(
            item_id="action-node-run",
            title="Run node",
            preview="Start a quiet background local node",
            details=[
                "Start the local node without blocking the interactive shell.",
                "",
                "Press Enter to execute `node run` now.",
            ],
            console_command="node run",
        ),
        NetworkCard(
            item_id="action-policy",
            title="Show policy",
            preview="Inspect relay and autostart policy",
            details=[
                "Show the current relay policy, strategy, autostart, and presence timings.",
                "",
                "Press Enter to execute `relay policy` now.",
            ],
            console_command="relay policy",
        ),
        NetworkCard(
            item_id="action-add-peer",
            title="Add peer",
            preview="Prepare an inline peer add command",
            details=[
                "Use the inline box below to add a direct peer without leaving the interactive UI.",
                "",
                "Press Enter to prefill `peer add ` in the network console.",
            ],
            compose_seed="peer add ",
        ),
        NetworkCard(
            item_id="action-add-relay",
            title="Add relay",
            preview="Prepare an inline relay add command",
            details=[
                "Use the inline box below to add a relay from the interactive UI.",
                "",
                "Press Enter to prefill `relay add ` in the network console.",
            ],
            compose_seed="relay add ",
        ),
        NetworkCard(
            item_id="action-storage-status",
            title="Storage status",
            preview="Inspect retained and prunable objects",
            details=[
                "Show storage retention counts, reasons, and prunable totals.",
                "",
                "Press Enter to execute `storage status` now.",
            ],
            console_command="storage status",
        ),
        NetworkCard(
            item_id="action-storage-prune",
            title="Dry-run prune",
            preview="Preview which objects would be removed",
            details=[
                "Run a dry-run prune so you can inspect object IDs before applying changes.",
                "",
                "Press Enter to execute `storage prune` now.",
            ],
            console_command="storage prune",
        ),
        NetworkCard(
            item_id="action-storage-inspect",
            title="Inspect object",
            preview="Prepare a storage inspect command",
            details=[
                "Use the inline box below to inspect why a specific object is retained.",
                "",
                "Press Enter to prefill `storage inspect ` in the network console.",
            ],
            compose_seed="storage inspect ",
        ),
        NetworkCard(
            item_id="status",
            title="Status",
            preview=f"{len(targets)} discovery target(s)",
            details=[
                f"Strategy: {policy['strategy']}",
                f"Relay: {'on' if policy['relay_enabled'] else 'off'}",
                f"Autostart: {'on' if policy['node_autostart'] else 'off'}",
                f"Public endpoint: {policy['public_endpoint'] or '(not set)'}",
                f"Presence TTL: {policy['presence_ttl_seconds']}s",
                f"Presence refresh: {policy['presence_refresh_seconds']}s",
            ],
        ),
        NetworkCard(
            item_id="local-node",
            title="Local node",
            preview=runtime["url"] if runtime is not None else "Not running",
            details=runtime_lines,
        ),
        NetworkCard(
            item_id="peers",
            title="Peers",
            preview=f"{len(peers)} configured",
            details=["Peers", "", *(peers or ["No peers configured."])],
        ),
        NetworkCard(
            item_id="relays",
            title="Relays",
            preview=f"{len(relays)} configured",
            details=["Relays", "", *(relays or ["No relays configured."])],
        ),
        NetworkCard(
            item_id="targets",
            title="Targets",
            preview=f"{len(targets)} reachable path(s)",
            details=[
                "Discovery targets",
                "",
                *(target_details or ["No targets configured."]),
            ],
        ),
    ]


def _load_search_cards(query: str, actor_pubkey: str | None) -> list[SearchCard]:
    """Build search results for a username or handle query."""

    lookup = query.strip().lower()
    if not lookup:
        return []

    exact_matches = find_identity_matches(query)
    candidates = exact_matches if exact_matches else []
    if not candidates:
        for user in get_known_users():
            username = user["username"].lower()
            handle = build_identity_handle(user["username"], user["pubkey"]).lower()
            if lookup in username or lookup in handle:
                candidates.append(user)

    deduped: dict[str, SearchCard] = {}
    for user in candidates:
        handle = build_identity_handle(user["username"], user["pubkey"])
        followed = (
            is_following(actor_pubkey, user["pubkey"])
            if actor_pubkey is not None and actor_pubkey != user["pubkey"]
            else False
        )
        deduped[user["pubkey"]] = SearchCard(
            title=f"@{user['username']}",
            preview=f"{handle} - {'following' if followed else 'known user'}",
            details=[
                f"Handle: {handle}",
                f"Pubkey: {user['pubkey']}",
                f"Status: {'Following' if followed else 'Not following'}",
                "",
                "Press Enter to open chat. Press `f` to follow or unfollow.",
            ],
            target_pubkey=user["pubkey"],
            target_username=user["username"],
            handle=handle,
        )

    return list(deduped.values())


def _parse_room_ttl(raw_ttl: str) -> float | None:
    """Parse a room TTL token like 15m or 2d."""

    token = raw_ttl.strip().lower()
    if not token:
        return None

    unit = token[-1]
    if unit.isdigit():
        value = int(token)
        multiplier = 1
    else:
        value_part = token[:-1]
        if not value_part.isdigit():
            raise ValueError(
                "Invalid ephemeral duration. Use values like 15s, 1m, 3h, or 2d."
            )
        value = int(value_part)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        multiplier = multipliers.get(unit)
        if multiplier is None:
            raise ValueError("Invalid ephemeral duration unit. Use s, m, h, or d.")

    if value <= 0:
        raise ValueError("Ephemeral duration must be greater than zero.")

    return float(value * multiplier)


class HomeScreen(Static):
    """First-pass Textual home screen backed by the canonical feed logic."""

    DEFAULT_CSS = """
    HomeScreen {
        height: 1fr;
    }

    #home-layout {
        height: 1fr;
    }

    #sidebar {
        width: 24;
        padding: 1 1;
        border: round $panel;
    }

    #feed-column, #detail-column {
        height: 1fr;
        padding: 1 1;
        border: round $panel;
    }

    #feed-list {
        height: 1fr;
        margin-top: 1;
    }

    #search-bar,
    #feed-composer {
        margin-top: 1;
    }

    #room-options {
        display: none;
        height: auto;
        margin-top: 1;
    }

    #room-private, #room-ephemeral {
        width: auto;
        margin-right: 1;
    }

    #room-ttl {
        width: 18;
    }

    #detail-body {
        margin-top: 1;
    }

    .muted {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_feed", "Refresh"),
        Binding("f", "toggle_feed", "Feed / Follow"),
        Binding("enter", "open_post", "Open"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.feed_type: FeedKind = "global"
        self._cards_by_id: dict[str, FeedCard] = {}
        self._feed_cards: list[FeedCard] = []
        self._chat_cards_by_id: dict[str, ChatCard] = {}
        self._chat_cards: list[ChatCard] = []
        self._room_cards_by_id: dict[str, RoomCard] = {}
        self._room_cards: list[RoomCard] = []
        self._profile_cards_by_id: dict[str, ProfileCard] = {}
        self._profile_cards: list[ProfileCard] = []
        self._network_cards_by_id: dict[str, NetworkCard] = {}
        self._network_cards: list[NetworkCard] = []
        self._search_cards: list[SearchCard] = []
        self._search_query = ""
        self.active_section = ""

    def compose(self) -> ComposeResult:
        """Render the initial home layout."""

        with Horizontal(id="home-layout"):
            with Vertical(id="sidebar"):
                yield Label("Beep", id="sidebar-title")
                yield Sidebar()
            with Vertical(id="feed-column"):
                yield Label("Home Feed", id="feed-title")
                yield Static(
                    "Arrow keys move through posts. Press `f` to switch feeds or Enter to open.",
                    id="feed-hint",
                    classes="muted",
                )
                yield Input(
                    placeholder="Search by username or handle",
                    id="search-bar",
                )
                yield ListView(id="feed-list")
                yield Input(
                    placeholder="Write a post and press Enter",
                    id="feed-composer",
                )
                with Horizontal(id="room-options"):
                    yield Checkbox("Private", id="room-private")
                    yield Checkbox("Ephemeral", id="room-ephemeral")
                    yield Input(
                        placeholder="TTL e.g. 15m",
                        id="room-ttl",
                    )
            with Vertical(id="detail-column"):
                yield Label("Post", id="detail-title")
                yield Static(
                    "Select a post to see more details.",
                    id="detail-body",
                )

    def on_mount(self) -> None:
        """Populate the initial home timeline."""

        self._activate_section("home")

    def action_refresh_feed(self) -> None:
        """Refresh the current home timeline."""

        if self.active_section in {"home", "following"}:
            self._refresh_feed()
            return
        if self.active_section == "messages":
            self._refresh_messages()
            return
        if self.active_section == "rooms":
            self._refresh_rooms()
            return
        if self.active_section == "profile":
            self._refresh_profile()
            return
        if self.active_section == "search":
            self._refresh_search()
            return
        if self.active_section == "network":
            self._refresh_network()

    def action_toggle_feed(self) -> None:
        """Switch between global and followed feed views."""

        if self.active_section == "profile":
            self.action_toggle_follow()
            return
        if self.active_section == "search":
            self.action_toggle_search_follow()
            return
        if self.active_section not in {"home", "following"}:
            return
        self.feed_type = "followed" if self.feed_type == "global" else "global"
        self.active_section = "following" if self.feed_type == "followed" else "home"
        self._sync_sidebar_selection(self.active_section)
        self._refresh_feed()

    def action_toggle_follow(self) -> None:
        """Follow or unfollow the selected known user from the profile view."""

        if self.active_section != "profile":
            return

        session = load_session()
        if session is None:
            self.query_one("#detail-title", Label).update("Profile")
            self.query_one("#detail-body", Static).update(
                "Log in to follow or unfollow users from the interactive shell."
            )
            return

        card = self._selected_profile_card()
        if card is None or not card.followable or card.target_pubkey is None:
            return

        try:
            if is_following(session["pubkey"], card.target_pubkey):
                unfollow(session["pubkey"], card.target_pubkey)
                action_text = f"You no longer follow @{card.target_username}."
            else:
                follow(session["pubkey"], card.target_pubkey)
                action_text = f"You now follow @{card.target_username}."
        except Exception as exc:
            self.query_one("#detail-title", Label).update(card.title)
            self.query_one("#detail-body", Static).update(
                f"Could not update follow state: {exc}"
            )
            return

        self._refresh_profile()
        list_view = self.query_one("#feed-list", ListView)
        for index, refreshed_card in enumerate(self._profile_cards):
            if refreshed_card.item_id == card.item_id:
                list_view.index = index
                break
        self.query_one("#detail-title", Label).update(card.title)
        self.query_one("#detail-body", Static).update(action_text)

    def action_logout_session(self) -> None:
        """Log out from the profile section and return to the login screen."""

        if self.active_section != "profile":
            return

        session = load_session()
        if session is None:
            self.query_one("#detail-title", Label).update("Profile")
            self.query_one("#detail-body", Static).update("No user is currently logged in.")
            return

        clear_session()
        if hasattr(self.app, "show_login_shell"):
            self.app.show_login_shell()

    def action_toggle_search_follow(self) -> None:
        """Follow or unfollow the selected search result."""

        if self.active_section != "search":
            return

        session = load_session()
        if session is None:
            self.query_one("#detail-title", Label).update("Search")
            self.query_one("#detail-body", Static).update(
                "Log in to follow or unfollow users from search."
            )
            return

        card = self._selected_search_card()
        if card is None:
            return

        if card.target_pubkey == session["pubkey"]:
            self.query_one("#detail-title", Label).update(card.title)
            self.query_one("#detail-body", Static).update(
                "You cannot follow yourself."
            )
            return

        try:
            if is_following(session["pubkey"], card.target_pubkey):
                unfollow(session["pubkey"], card.target_pubkey)
                action_text = f"You no longer follow @{card.target_username}."
            else:
                follow(session["pubkey"], card.target_pubkey)
                action_text = f"You now follow @{card.target_username}."
        except Exception as exc:
            self.query_one("#detail-title", Label).update(card.title)
            self.query_one("#detail-body", Static).update(
                f"Could not update follow state: {exc}"
            )
            return

        self._refresh_search()
        self.query_one("#detail-title", Label).update(card.title)
        self.query_one("#detail-body", Static).update(action_text)

    def action_open_post(self) -> None:
        """Open the selected item in a dedicated detail screen."""

        list_view = self.query_one("#feed-list", ListView)
        if self.active_section in {"home", "following"}:
            card = self._selected_feed_card()
            if card is None:
                return
            self.app.push_screen(PostScreen(card.object_id))
            return
        if self.active_section == "network":
            card = self._selected_network_card()
            if card is None:
                return
            if card.console_command:
                self._run_network_console_command(card.console_command)
                return
            if card.compose_seed is not None:
                composer = self.query_one("#feed-composer", Input)
                composer.value = card.compose_seed
                composer.focus()
                self.query_one("#detail-title", Label).update(card.title)
                self.query_one("#detail-body", Static).update("\n".join(card.details))
                return
        if self.active_section == "search":
            card = self._selected_search_card()
            if card is None:
                return
            self._open_chat_with_user(card.target_username)
            return
        if self.active_section == "messages":
            card = self._selected_chat_card()
            if card is None:
                return
            self.app.push_screen(ChatScreen(card.peer_username))
            return
        if self.active_section == "rooms":
            card = self._selected_room_card()
            if card is None:
                return
            self._open_or_create_room(card.room_name)
            return

    def _refresh_feed(self) -> None:
        """Rebuild the visible feed list from stored objects."""

        if self.active_section not in {"home", "following"}:
            return

        cards = _load_feed_cards(self.feed_type)
        self._feed_cards = cards
        self._cards_by_id = {card.object_id: card for card in cards}

        feed_title = self.query_one("#feed-title", Label)
        feed_title.update(
            "Home Feed" if self.feed_type == "global" else "Following Feed"
        )
        self.query_one("#feed-hint", Static).update(
            "Arrow keys move through posts. Press `f` to switch feeds, Enter to open, or use the composer below."
        )
        self._set_search_state(
            enabled=False,
            placeholder="Search by username or handle",
            visible=False,
        )
        self._set_room_options_state(visible=False)
        self._set_composer_state(
            enabled=True,
            placeholder="Write a post and press Enter",
            visible=True,
        )

        list_view = self.query_one("#feed-list", ListView)
        list_view.clear()

        if not cards:
            self.query_one("#detail-title", Label).update("Post")
            self.query_one("#detail-body", Static).update(
                'No posts yet. Try `beep post "hello"` in command mode.'
            )
            return

        for index, card in enumerate(cards):
            label = Label("\n".join(card.display_lines))
            list_view.append(ListItem(label))

        self._show_detail(cards[0].object_id)

    def _show_detail(self, object_id: str) -> None:
        """Render the selected post in the detail pane."""

        card = self._cards_by_id.get(object_id)
        if card is None:
            return

        self.query_one("#detail-title", Label).update(
            f"@{card.author_name} - {card.relative_timestamp}"
        )
        self.query_one("#detail-body", Static).update(
            "\n".join(
                [
                    f"Handle: {card.author_handle}",
                    f"Object: {card.object_id}",
                    *card.context_lines,
                ]
            )
        )

    def _refresh_messages(self) -> None:
        """Populate the direct-chat list/detail view."""

        self._chat_cards_by_id = {
            card.peer_username: card for card in _load_chat_cards()
        }
        self._chat_cards = list(self._chat_cards_by_id.values())

        self.query_one("#feed-title", Label).update("Messages")
        self.query_one("#detail-title", Label).update("Chat")
        self.query_one("#feed-hint", Static).update(
            "Arrow keys move through chats. Press Enter to open a thread."
        )
        self._set_search_state(
            enabled=False,
            placeholder="Search by username or handle",
            visible=False,
        )
        self._set_room_options_state(visible=False)
        self._set_composer_state(
            enabled=True,
            placeholder="Type a username or handle and press Enter to open chat",
            visible=True,
        )

        list_view = self.query_one("#feed-list", ListView)
        list_view.clear()

        if not self._chat_cards_by_id:
            self.query_one("#detail-body", Static).update(
                "\n".join(
                    [
                        "No direct chats yet.",
                        "",
                        "Use command mode to start one:",
                        "  beep chat <username>",
                    ]
                )
            )
            return

        for card in self._chat_cards:
            list_view.append(ListItem(Label(f"@{card.peer_username}\n{card.preview}")))

        self._show_chat_detail(self._chat_cards[0].peer_username)

    def _show_chat_detail(self, peer_username: str) -> None:
        """Render selected chat detail in the side pane."""

        card = self._chat_cards_by_id.get(peer_username)
        if card is None:
            return
        self.query_one("#detail-title", Label).update(f"Chat @{peer_username}")
        self.query_one("#detail-body", Static).update(
            "\n".join(
                [
                    f"Status: {card.status}",
                    "",
                    *(card.messages or ["No messages yet."]),
                ]
            )
        )

    def _refresh_rooms(self) -> None:
        """Populate the room list/detail view."""

        self._room_cards_by_id = {card.room_name: card for card in _load_room_cards()}
        self._room_cards = list(self._room_cards_by_id.values())

        self.query_one("#feed-title", Label).update("Rooms")
        self.query_one("#detail-title", Label).update("Room")
        self.query_one("#feed-hint", Static).update(
            "Arrow keys move through rooms. Press Enter to open one, or create a room with the controls below."
        )
        self._set_search_state(
            enabled=False,
            placeholder="Search by username or handle",
            visible=False,
        )
        self._set_room_options_state(visible=True)
        self._set_composer_state(
            enabled=True,
            placeholder="Type a room name and press Enter to open or create it",
            visible=True,
        )
        self.query_one("#feed-composer", Input).focus()

        list_view = self.query_one("#feed-list", ListView)
        list_view.clear()

        if not self._room_cards_by_id:
            self.query_one("#detail-body", Static).update(
                "\n".join(
                    [
                        "No rooms available yet.",
                        "",
                        "Use command mode to create one:",
                        "  beep room <name>",
                    ]
                )
            )
            return

        for card in self._room_cards:
            list_view.append(ListItem(Label(f"{card.room_name}\n{card.preview}")))

        self._show_room_detail(self._room_cards[0].room_name)

    def _show_room_detail(self, room_name: str) -> None:
        """Render selected room detail in the side pane."""

        card = self._room_cards_by_id.get(room_name)
        if card is None:
            return
        self.query_one("#detail-title", Label).update(room_name)
        self.query_one("#detail-body", Static).update("\n".join(card.details))

    def _refresh_profile(self) -> None:
        """Populate the profile list/detail view."""

        self._profile_cards_by_id = {
            card.item_id: card for card in _load_profile_cards()
        }

        self.query_one("#feed-title", Label).update("Profile")
        self.query_one("#detail-title", Label).update("Profile")
        self.query_one("#feed-hint", Static).update(
            "Arrow keys move through profile sections. Press `f` to follow users or `l` to log out."
        )
        self._set_search_state(
            enabled=False,
            placeholder="Search by username or handle",
            visible=False,
        )
        self._set_room_options_state(visible=False)
        self._set_composer_state(
            enabled=False,
            placeholder="Write a post and press Enter",
            visible=False,
        )

        list_view = self.query_one("#feed-list", ListView)
        list_view.clear()

        self._profile_cards = list(self._profile_cards_by_id.values())

        if not self._profile_cards_by_id:
            self.query_one("#detail-body", Static).update(
                "Profile data is unavailable."
            )
            return

        for card in self._profile_cards:
            list_view.append(ListItem(Label(f"{card.title}\n{card.preview}")))

        self._show_profile_detail(self._profile_cards[0].item_id)

    def _refresh_search(self) -> None:
        """Populate the search list/detail view."""

        session = load_session()
        actor_pubkey = session["pubkey"] if session is not None else None
        self._search_cards = _load_search_cards(self._search_query, actor_pubkey)
        search_bar = self.query_one("#search-bar", Input)

        self.query_one("#feed-title", Label).update("Search")
        self.query_one("#detail-title", Label).update("Search")
        self.query_one("#feed-hint", Static).update(
            "Search username or handle below. Press Enter on a result to open chat."
        )
        self._set_search_state(
            enabled=True,
            placeholder="Search by username or handle",
            visible=True,
        )
        self._set_room_options_state(visible=False)
        self._set_composer_state(
            enabled=False,
            placeholder="Write a post and press Enter",
            visible=False,
        )

        list_view = self.query_one("#feed-list", ListView)
        list_view.clear()

        if not self._search_query.strip():
            self.query_one("#detail-body", Static).update(
                "Search for a username or handle to find known users."
            )
            search_bar.focus()
            return

        if not self._search_cards:
            self.query_one("#detail-body", Static).update(
                f"No known users match '{self._search_query}'."
            )
            search_bar.focus()
            return

        for card in self._search_cards:
            list_view.append(ListItem(Label(f"{card.title}\n{card.preview}")))

        list_view.index = 0
        list_view.focus()
        self._show_search_detail(self._search_cards[0])

    def _show_profile_detail(self, item_id: str) -> None:
        """Render selected profile detail in the side pane."""

        card = self._profile_cards_by_id.get(item_id)
        if card is None:
            return
        self.query_one("#detail-title", Label).update(card.title)
        self.query_one("#detail-body", Static).update("\n".join(card.details))

    def _refresh_network(self) -> None:
        """Populate the network list/detail view."""

        self._network_cards_by_id = {
            card.item_id: card for card in _load_network_cards()
        }
        self._network_cards = list(self._network_cards_by_id.values())

        self.query_one("#feed-title", Label).update("Network")
        self.query_one("#detail-title", Label).update("Network")
        self.query_one("#feed-hint", Static).update(
            "Arrow keys move through network sections. Use the box below for inline network commands."
        )
        self._set_search_state(
            enabled=False,
            placeholder="Search by username or handle",
            visible=False,
        )
        self._set_room_options_state(visible=False)
        self._set_composer_state(
            enabled=True,
            placeholder="Try: status | sync | connect | node run | storage status | relay policy",
            visible=True,
        )

        list_view = self.query_one("#feed-list", ListView)
        list_view.clear()

        for index, card in enumerate(self._network_cards):
            list_view.append(ListItem(Label(f"{card.title}\n{card.preview}")))

        if self._network_cards:
            self._show_network_detail(self._network_cards[0].item_id)

    def _show_network_detail(self, item_id: str) -> None:
        """Render selected network detail in the side pane."""

        card = self._network_cards_by_id.get(item_id)
        if card is None:
            return
        self.query_one("#detail-title", Label).update(card.title)
        self.query_one("#detail-body", Static).update("\n".join(card.details))

    def _show_search_detail(self, card: SearchCard) -> None:
        """Render selected search result detail in the side pane."""

        self.query_one("#detail-title", Label).update(card.title)
        self.query_one("#detail-body", Static).update("\n".join(card.details))

    def _activate_section(self, section: str) -> None:
        """Switch the active sidebar section."""

        if section == self.active_section:
            return

        self.active_section = section
        self._apply_section_layout(section)
        self._sync_sidebar_selection(section)
        if section == "home":
            self.feed_type = "global"
            self._refresh_feed()
            return
        if section == "following":
            self.feed_type = "followed"
            self._refresh_feed()
            return
        if section == "messages":
            self._refresh_messages()
            return
        if section == "rooms":
            self._refresh_rooms()
            return
        if section == "profile":
            self._refresh_profile()
            return
        if section == "search":
            self._refresh_search()
            return
        if section == "network":
            self._refresh_network()
            return

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Open selected items with Enter across supported sections."""

        if event.list_view.id == "feed-list":
            self.action_open_post()
            return

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update list/detail panes when the selection changes."""

        if event.list_view.id == "sidebar-nav":
            item = event.item
            if item is None or item.id is None:
                return
            self._activate_section(item.id)
            return

        item = event.item
        if item is None:
            return
        if self.active_section in {"home", "following"}:
            card = self._selected_feed_card()
            if card is None:
                return
            self._show_detail(card.object_id)
            return
        if self.active_section == "search":
            card = self._selected_search_card()
            if card is None:
                return
            self._show_search_detail(card)
            return
        if self.active_section == "messages":
            card = self._selected_chat_card()
            if card is None:
                return
            self._show_chat_detail(card.peer_username)
            return
        if self.active_section == "rooms":
            card = self._selected_room_card()
            if card is None:
                return
            self._show_room_detail(card.room_name)
            return
        if self.active_section == "profile":
            card = self._selected_profile_card()
            if card is None:
                return
            self._show_profile_detail(card.item_id)
            return
        if self.active_section == "network":
            card = self._selected_network_card()
            if card is None:
                return
            self._show_network_detail(card.item_id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Create a new post from the inline feed composer."""

        if event.input.id == "search-bar":
            if self.active_section != "search":
                return
            self._search_query = event.value.strip()
            self._refresh_search()
            return

        if event.input.id != "feed-composer":
            return

        content = event.value.strip()
        if not content:
            return

        if self.active_section == "network":
            self._run_network_console_command(content)
            event.input.value = ""
            return
        if self.active_section == "messages":
            self._open_chat_with_query(content)
            event.input.value = ""
            return
        if self.active_section == "rooms":
            self._open_or_create_room(content)
            event.input.value = ""
            return
        if self.active_section == "search":
            search_bar = self.query_one("#search-bar", Input)
            search_bar.value = content
            self._search_query = content
            self._refresh_search()
            return

        if self.active_section not in {"home", "following"}:
            event.input.value = ""
            return

        session = load_session()
        if session is None:
            self.query_one("#detail-title", Label).update("Post")
            self.query_one("#detail-body", Static).update(
                "Log in to create posts from the interactive shell."
            )
            return

        try:
            create_post(session["pubkey"], content)
        except Exception as exc:
            self.query_one("#detail-title", Label).update("Post")
            self.query_one("#detail-body", Static).update(
                f"Could not create post: {exc}"
            )
            return

        event.input.value = ""
        self._refresh_feed()

    def _set_composer_state(
        self,
        *,
        enabled: bool,
        placeholder: str,
        visible: bool,
    ) -> None:
        """Enable or disable the feed composer for the current section."""

        composer = self.query_one("#feed-composer", Input)
        composer.display = visible
        composer.disabled = not enabled
        composer.placeholder = placeholder
        if not enabled:
            composer.value = ""

    def _set_search_state(
        self,
        *,
        enabled: bool,
        placeholder: str,
        visible: bool,
    ) -> None:
        """Enable or disable the dedicated search bar."""

        search_bar = self.query_one("#search-bar", Input)
        search_bar.display = visible
        search_bar.disabled = not enabled
        search_bar.placeholder = placeholder
        if not visible:
            search_bar.value = ""
        elif self.active_section == "search":
            search_bar.value = self._search_query

    def _set_room_options_state(self, *, visible: bool) -> None:
        """Show or hide inline room creation options."""

        options = self.query_one("#room-options", Horizontal)
        options.display = visible
        if not visible:
            self.query_one("#room-private", Checkbox).value = False
            self.query_one("#room-ephemeral", Checkbox).value = False
            self.query_one("#room-ttl", Input).value = ""

    def _run_network_console_command(self, raw_command: str) -> None:
        """Run a network/relay/peer command from the inline network composer."""

        parts = raw_command.split()
        if not parts:
            return

        if parts[0] == "beep":
            parts = parts[1:]
            if not parts:
                self._refresh_network()
                self.query_one("#detail-title", Label).update("Network Console")
                self.query_one("#detail-body", Static).update(
                    "This box only supports network commands.\n"
                    "Try: status | check | setup --relay <url> | peer add <url> | relay policy"
                )
                return

        session = load_session()
        state = SimpleNamespace(
            user=session["username"] if session else None,
            pubkey=session["pubkey"] if session else None,
        )
        output = io.StringIO()

        try:
            with redirect_stdout(output):
                if parts[0] == "network":
                    network_dispatch("network", " ".join(parts[1:]), state)
                elif parts[0] == "connect":
                    connect_dispatch("connect", " ".join(parts[1:]), state)
                elif parts[0] == "relay":
                    relay_dispatch("relay", " ".join(parts[1:]), state)
                elif parts[0] == "peer":
                    self._run_peer_console_command(parts[1:], output)
                elif parts[0] == "sync":
                    SyncCommand.dispatch("sync", " ".join(parts[1:]), state)
                elif parts[0] == "storage":
                    storage_dispatch("storage", " ".join(parts[1:]), state)
                elif parts[0] == "node":
                    self._run_node_console_command(parts[1:], state, output)
                elif parts[0] in {"status", "check", "setup"}:
                    network_dispatch("network", " ".join(parts), state)
                else:
                    print(
                        "This box only supports node, network, sync, connect, storage, relay, or peer commands.\n"
                        "Try: status | sync | connect | node run | storage status | peer add <url> | relay policy"
                    )
        except Exception as exc:
            output.write(f"[NETWORK] Command failed: {exc}\n")

        rendered = output.getvalue().strip() or "[NETWORK] No output."
        self._refresh_network()
        self.query_one("#detail-title", Label).update("Network Console")
        self.query_one("#detail-body", Static).update(rendered)

    def _run_node_console_command(
        self,
        parts: list[str],
        state: SimpleNamespace,
        output: io.StringIO,
    ) -> None:
        """Start or describe the local node from the network section."""

        from network.node_manager import ensure_background_node

        if not parts or parts[0] != "run":
            output.write("Usage: node run\n")
            return
        if state.user is None or state.pubkey is None:
            output.write("You must be logged in to run a node.\n")
            return
        if "--port" in parts:
            output.write(
                "Interactive node launch uses an automatic background port.\n"
                "Use command mode if you need a manual `--port` selection.\n"
            )
            return

        runtime = ensure_background_node(state.user, state.pubkey)
        if runtime is None:
            output.write("Could not start the local background node.\n")
            return

        output.write(
            f"Local node running at {runtime['url']} (pid {runtime['pid']}).\n"
        )

    def _run_peer_console_command(
        self,
        parts: list[str],
        output: io.StringIO,
    ) -> None:
        """Handle simple peer commands inline inside the network section."""

        from network.peers import add_peer, load_peers, remove_peer

        if len(parts) >= 2 and parts[0] == "add":
            peer_url = add_peer(parts[1])
            output.write(f"peer added: {peer_url}\n")
            return
        if len(parts) >= 2 and parts[0] == "remove":
            peer_url = remove_peer(parts[1])
            output.write(f"peer removed: {peer_url}\n")
            return
        if parts and parts[0] == "list":
            peers = load_peers()
            if not peers:
                output.write("No peers configured.\n")
                return
            output.write("Peers:\n")
            for peer in peers:
                output.write(f" - {peer}\n")
            return
        output.write("Usage: peer add <url> | peer remove <url> | peer list\n")

    def _selected_feed_card(self) -> FeedCard | None:
        """Return the currently highlighted feed card."""

        list_view = self.query_one("#feed-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._feed_cards):
            return None
        return self._feed_cards[index]

    def _selected_chat_card(self) -> ChatCard | None:
        """Return the currently highlighted chat card."""

        list_view = self.query_one("#feed-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._chat_cards):
            return None
        return self._chat_cards[index]

    def _selected_network_card(self) -> NetworkCard | None:
        """Return the currently highlighted network card."""

        list_view = self.query_one("#feed-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._network_cards):
            return None
        return self._network_cards[index]

    def _selected_room_card(self) -> RoomCard | None:
        """Return the currently highlighted room card."""

        list_view = self.query_one("#feed-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._room_cards):
            return None
        return self._room_cards[index]

    def _selected_profile_card(self) -> ProfileCard | None:
        """Return the currently highlighted profile card."""

        list_view = self.query_one("#feed-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._profile_cards):
            return None
        return self._profile_cards[index]

    def _selected_search_card(self) -> SearchCard | None:
        """Return the currently highlighted search result."""

        list_view = self.query_one("#feed-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._search_cards):
            return None
        return self._search_cards[index]

    def _sync_sidebar_selection(self, section: str) -> None:
        """Keep sidebar selection aligned with the active section."""

        try:
            sidebar = self.query_one("#sidebar-nav", ListView)
        except Exception:
            return
        for index, child in enumerate(sidebar.children):
            if child.id == section:
                sidebar.index = index
                break

    def _apply_section_layout(self, section: str) -> None:
        """Adjust the right-side detail pane by section."""

        detail_column = self.query_one("#detail-column", Vertical)
        if section in {"home", "following", "messages", "rooms", "search"}:
            detail_column.display = False
            return

        detail_column.display = True
        detail_column.styles.width = 34

    def _open_chat_with_query(self, raw_query: str) -> None:
        """Resolve a user query and open a direct chat if possible."""

        query = raw_query.strip()
        if not query:
            return

        matches = find_identity_matches(query)
        if not matches:
            self.query_one("#detail-title", Label).update("Messages")
            self.query_one("#detail-body", Static).update(
                f"No known user matches '{query}'. Try Search first."
            )
            return
        if len(matches) > 1:
            handles = [
                build_identity_handle(match["username"], match["pubkey"])
                for match in matches
            ]
            self.query_one("#detail-title", Label).update("Messages")
            self.query_one("#detail-body", Static).update(
                "\n".join(
                    [
                        f"'{query}' is ambiguous. Use a handle:",
                        "",
                        *handles,
                    ]
                )
            )
            return

        self._open_chat_with_user(matches[0]["username"])

    def _open_chat_with_user(self, username: str) -> None:
        """Create and open a direct chat with a known user."""

        session = load_session()
        if session is None:
            self.query_one("#detail-title", Label).update("Messages")
            self.query_one("#detail-body", Static).update(
                "Log in to open direct chats."
            )
            return
        if username == session["username"]:
            self.query_one("#detail-title", Label).update("Messages")
            self.query_one("#detail-body", Static).update(
                "You cannot chat with yourself."
            )
            return

        try:
            ChatService().create_chat(None, session["username"], username)
        except Exception as exc:
            self.query_one("#detail-title", Label).update("Messages")
            self.query_one("#detail-body", Static).update(
                f"Could not open chat: {exc}"
            )
            return

        self.app.push_screen(ChatScreen(username))

    def _open_or_create_room(self, raw_name: str) -> None:
        """Join an existing room or create a new one from the rooms section."""

        room_name = raw_name.strip()
        if not room_name:
            return

        session = load_session()
        if session is None:
            self.query_one("#feed-hint", Static).update(
                "Log in first, then create or join a room from here."
            )
            self.query_one("#detail-title", Label).update("Rooms")
            self.query_one("#detail-body", Static).update(
                "Log in to open or create rooms."
            )
            return

        room_service = RoomService()
        try:
            room = room_service.build_room_state(room_name)
            if room is None:
                private = self.query_one("#room-private", Checkbox).value
                ephemeral = self.query_one("#room-ephemeral", Checkbox).value
                ttl_input = self.query_one("#room-ttl", Input).value
                ttl = None
                if ephemeral:
                    ttl = (
                        _parse_room_ttl(ttl_input)
                        if ttl_input.strip()
                        else float(EPHEMERAL_TTL_SECONDS)
                    )
                room_service.create_room(
                    room_name,
                    session["username"],
                    private=private,
                    ttl=ttl,
                )
                self.query_one("#feed-hint", Static).update(
                    f"Created room {room_name}. Opening it now."
                )
            else:
                room_service.join_room(room_name, session["username"])
                self.query_one("#feed-hint", Static).update(
                    f"Joined room {room_name}. Opening it now."
                )
        except Exception as exc:
            self.query_one("#feed-hint", Static).update(
                f"Could not open room: {exc}"
            )
            self.query_one("#detail-title", Label).update("Rooms")
            self.query_one("#detail-body", Static).update(
                f"Could not open room: {exc}"
            )
            return

        self.query_one("#feed-composer", Input).value = ""
        self.app.push_screen(RoomScreen(room_name))
