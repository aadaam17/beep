# network/peers.py

import json
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urlunparse

PEER_FILE = Path.home() / ".beep" / "peers.json"
PEER_FILE.parent.mkdir(parents=True, exist_ok=True)


def normalize_peer_url(peer_url: str) -> str:
    peer_url = peer_url.strip()
    if not peer_url:
        raise ValueError("Peer URL cannot be empty")

    if "://" not in peer_url:
        peer_url = f"http://{peer_url}"

    parsed = urlparse(peer_url)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname

    if not hostname:
        raise ValueError("Peer URL must include a host")

    if hostname == "0.0.0.0":
        hostname = "127.0.0.1"

    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"

    normalized = urlunparse((scheme, netloc, "", "", "", ""))
    return normalized.rstrip("/")


def load_peers() -> list[str]:
    if not PEER_FILE.exists():
        return []

    raw = PEER_FILE.read_text().strip()
    if not raw:
        return []

    try:
        peers = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(peers, list):
        return []

    normalized: list[str] = []
    seen = set()

    for peer in peers:
        if not isinstance(peer, str):
            continue
        try:
            candidate = normalize_peer_url(peer)
        except ValueError:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    if normalized != peers:
        save_peers(normalized)

    return normalized


def save_peers(peers: Iterable[str]) -> None:
    normalized: list[str] = []
    seen = set()

    for peer in peers:
        candidate = normalize_peer_url(peer)
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    PEER_FILE.write_text(json.dumps(normalized, indent=2))


def add_peer(peer_url: str) -> str:
    peer_url = normalize_peer_url(peer_url)
    peers = load_peers()
    if peer_url not in peers:
        peers.append(peer_url)
    save_peers(peers)
    return peer_url


def remove_peer(peer_url: str) -> str:
    peer_url = normalize_peer_url(peer_url)
    peers = load_peers()
    peers = [p for p in peers if p != peer_url]
    save_peers(peers)
    return peer_url
