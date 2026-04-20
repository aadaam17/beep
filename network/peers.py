# network/peers.py

import json
from pathlib import Path

PEER_FILE = Path.home() / ".beep" / "peers.json"
PEER_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_peers():
    if not PEER_FILE.exists():
        return []
    return json.loads(PEER_FILE.read_text())


def save_peers(peers):
    PEER_FILE.write_text(json.dumps(peers, indent=2))


def add_peer(peer_url: str):
    peers = load_peers()
    if peer_url not in peers:
        peers.append(peer_url)
    save_peers(peers)


def remove_peer(peer_url: str):
    peers = load_peers()
    peers = [p for p in peers if p != peer_url]
    save_peers(peers)