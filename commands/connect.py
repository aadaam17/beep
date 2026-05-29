# commands/connect.py
"""Identity handle display and resolution commands."""

from __future__ import annotations

from core.identity import build_identity_handle, find_identity_matches
from core.types import CommandState
from network.peers import add_peer, load_peers
from network.query import resolve_identity
from network.reachability import probe_endpoint
from network.sync import sync
from network.node_manager import load_node_runtime
from storage.network_policy import load_network_policy, order_network_targets, relay_enabled
from storage.profile import get_user
from storage.relay import add_relay, load_relays


def dispatch(cmd: str, args: str, state: CommandState) -> None:
    """Handle Beep identity handle sharing and known-user resolution."""

    if cmd != "connect":
        return

    identifier = (args or "").strip()
    if not identifier or identifier == "status":
        _print_local_handle(state)
        return

    matches = find_identity_matches(identifier)
    if not matches:
        targets = _discovery_targets()
        discovered = resolve_identity(
            identifier,
            targets,
        )
        if not discovered:
            _print_unknown_identity_message(identifier, targets)
            return
        if len(discovered) > 1:
            print(f"[CONNECT] '{identifier}' matched multiple peer-known identities:")
            for user in discovered:
                endpoint = user["endpoint"] or user["stale_endpoint"] or "no known endpoint"
                print(f" - {user['handle']} ({endpoint}, presence {user['presence_state']})")
            return

        discovered_user = discovered[0]
        endpoint = discovered_user["endpoint"]
        stale_endpoint = discovered_user["stale_endpoint"]
        presence_state = discovered_user["presence_state"]
        relay_hints = discovered_user["relay_hints"]
        policy = load_network_policy()

        if (
            policy["strategy"] == "relay-first"
            and relay_enabled()
            and relay_hints
        ):
            relay_url = add_relay(relay_hints[0])
            sync(verbose=False)
            print(f"[CONNECT] Added relay {relay_url}")
            print(
                f"[CONNECT] Found {discovered_user['handle']} through relay-assisted discovery."
            )
            if endpoint:
                _print_endpoint_observation(endpoint, presence_state)
            print(f"[CONNECT] You can now use: beep chat {discovered_user['handle']}")
            return

        if endpoint is not None:
            reachability = probe_endpoint(endpoint)
            if reachability == "reachable":
                peer_url = add_peer(endpoint)
                sync(verbose=False)
                print(f"[CONNECT] Added peer {peer_url}")
                print(f"[CONNECT] Connected to {discovered_user['handle']}")
                print(f"[CONNECT] You can now use: beep chat {discovered_user['handle']}")
                return
            print(
                f"[CONNECT] Found {discovered_user['handle']}, but the direct endpoint is currently down: {endpoint}"
            )
            if relay_hints and relay_enabled():
                relay_url = add_relay(relay_hints[0])
                sync(verbose=False)
                print(f"[CONNECT] Added relay {relay_url}")
                print(
                    f"[CONNECT] Falling back to relay-assisted discovery for {discovered_user['handle']}."
                )
                print(f"[CONNECT] You can now use: beep chat {discovered_user['handle']}")
                return
            print("[CONNECT] Try again later, or add a relay that knows this user.")
            return

        if endpoint is None:
            if presence_state == "stale":
                stale_label = stale_endpoint or "no saved endpoint"
                print(
                    f"[CONNECT] Found {discovered_user['handle']}, but the latest known direct endpoint is stale: {stale_label}"
                )
            elif presence_state == "none":
                print(
                    f"[CONNECT] Found {discovered_user['handle']}, but no direct presence is known right now."
                )
            if relay_hints and relay_enabled():
                relay_url = add_relay(relay_hints[0])
                sync(verbose=False)
                print(f"[CONNECT] Added relay {relay_url}")
                print(
                    f"[CONNECT] Found {discovered_user['handle']} through relay-assisted discovery."
                )
                print(f"[CONNECT] You can now use: beep chat {discovered_user['handle']}")
                return
            if relay_hints and not relay_enabled():
                print(
                    f"[CONNECT] Found {discovered_user['handle']}, but relay use is disabled by policy."
                )
                print("[CONNECT] Enable it with: beep relay policy set enabled on")
                return
            print(
                f"[CONNECT] Found {discovered_user['handle']}, but peers do not know a reachable endpoint yet."
            )
            return

    if len(matches) > 1:
        print(f"[CONNECT] '{identifier}' is ambiguous. Known matches:")
        for user in matches:
            handle = build_identity_handle(user["username"], user["pubkey"])
            print(f" - {handle} ({user['pubkey']})")
        return

    user = matches[0]
    handle = build_identity_handle(user["username"], user["pubkey"])
    print(f"[CONNECT] Known identity: {handle}")
    print(f"[CONNECT] Pubkey: {user['pubkey']}")
    print(f"[CONNECT] You can now use: beep chat {handle}")


def _print_local_handle(state: CommandState) -> None:
    """Print the active user's share handle."""

    if state.user is None:
        print("[CONNECT] Log in first or pass a known handle.")
        return

    user = get_user(state.user)
    if user is None:
        print(f"[CONNECT] Local identity '{state.user}' is unavailable.")
        return

    handle = build_identity_handle(user["username"], user["pubkey"])
    policy = load_network_policy()
    runtime = load_node_runtime()
    peers = load_peers()
    relays = load_relays()

    print(f"[CONNECT] Your Beep handle: {handle}")
    print(f"[CONNECT] Your pubkey: {user['pubkey']}")
    print(
        f"[CONNECT] Network strategy: {policy['strategy']} | "
        f"relay {'on' if policy['relay_enabled'] else 'off'} | "
        f"autostart {'on' if policy['node_autostart'] else 'off'}"
    )
    print(
        f"[CONNECT] Peers: {len(peers)} | Relays: {len(relays)} | "
        f"public endpoint: {policy['public_endpoint'] or '(not set)'}"
    )
    if runtime is not None:
        print(f"[CONNECT] Local node runtime: {runtime['url']}")
    if relays and policy["relay_enabled"]:
        print(f"[CONNECT] Relay-assisted discovery enabled via {len(relays)} relay(s)")
    if not peers and not relays:
        print("[CONNECT] No discovery targets configured yet.")
        print("[CONNECT] Add one with: beep peer add <url> or beep relay add <url>")


def _discovery_targets() -> list[str]:
    """Return deduplicated peers plus relays for connect-time discovery."""

    return order_network_targets(load_peers(), load_relays())


def _print_unknown_identity_message(identifier: str, targets: list[str]) -> None:
    """Explain why a connect lookup could not resolve an identity."""

    policy = load_network_policy()
    relays = load_relays()
    peers = load_peers()

    if not targets:
        print(f"[CONNECT] '{identifier}' is not known locally yet.")
        if not peers and not relays:
            print("[CONNECT] No peers or relays are configured, so discovery cannot start.")
            print("[CONNECT] Add one with: beep peer add <url> or beep relay add <url>")
            return
        if not peers and not policy["relay_enabled"] and relays:
            print("[CONNECT] Relay URLs exist, but relay use is disabled by policy.")
            print("[CONNECT] Enable it with: beep relay policy set enabled on")
            return
        if policy["strategy"] == "direct-only" and relays and not peers:
            print("[CONNECT] Strategy is direct-only, so relay discovery is intentionally skipped.")
            print("[CONNECT] Change it with: beep relay policy set strategy prefer-direct")
            return

    print(f"[CONNECT] '{identifier}' is not known locally or by current discovery targets.")
    print(
        f"[CONNECT] Checked {len(targets)} target(s) using strategy {policy['strategy']}."
    )
    print("[CONNECT] Try syncing, adding another peer, or adding a relay that knows this user.")


def _print_endpoint_observation(endpoint: str, presence_state: str) -> None:
    """Describe what is known about a direct endpoint."""

    if presence_state == "fresh":
        print(f"[CONNECT] Direct endpoint also known and fresh: {endpoint}")
    elif presence_state == "stale":
        print(f"[CONNECT] Direct endpoint is known but stale: {endpoint}")
    else:
        print(f"[CONNECT] Direct endpoint also known: {endpoint}")
