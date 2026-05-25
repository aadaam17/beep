"""Sidebar widgets for the Textual Beep app."""

from __future__ import annotations

from textual.widgets import Label, ListItem, ListView

SIDEBAR_ITEMS: list[tuple[str, str]] = [
    ("home", "Home"),
    ("following", "Following"),
    ("rooms", "Rooms"),
    ("messages", "Messages"),
    ("search", "Search"),
    ("profile", "Profile"),
    ("network", "Network"),
]


class Sidebar(ListView):
    """Simple navigation sidebar for the first Textual Beep shell."""

    def __init__(self) -> None:
        items = [
            ListItem(Label(label), id=item_id)
            for item_id, label in SIDEBAR_ITEMS
        ]
        super().__init__(*items, id="sidebar-nav")
