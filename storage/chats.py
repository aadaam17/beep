# storage/chats.py
"""Chat record storage and retrieval."""

from .fs import BeepFS
from core.types import ChatMessage, ChatRecord

fs = BeepFS()


def list_chats() -> list[str]:
    return fs.list_chats()


def read_chat(name: str) -> list[ChatMessage]:
    chat: ChatRecord | None = fs.read_chat(name)
    if not chat:
        return []
    return chat.get("messages", [])
