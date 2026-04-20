from .fs import BeepFS

fs = BeepFS()


def list_chats():
    return fs.list_chats()


def read_chat(name):
    chat = fs.read_chat(name)
    if not chat:
        return []
    return chat.get("messages", [])
