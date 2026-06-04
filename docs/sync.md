# Sync

Beep sync is object replication between local nodes, direct peers, and relays.

## Network Targets

Targets come from configured peers and relays. Relay policy controls whether
relays are used and how targets are ordered.

Strategies:

```text
prefer-direct
direct-only
relay-first
```

Commands:

```text
beep peer add <url>
beep peer remove <url>
beep peer list
beep relay add <url>
beep relay remove <url>
beep relay list
beep relay policy
beep network status
beep network check
beep sync
beep node status
beep node enable
beep node disable
```

## Node Endpoints

The node runtime exposes object exchange endpoints:

```text
GET  /objects
GET  /object/{object_id}
POST /object
GET  /inventory
GET  /objects/by_author/{author}
GET  /objects/by_type/{type}
GET  /objects/recent
GET  /resolve/{identifier}
```

## Sync Flow

For each configured target, Beep:

1. Fetches the remote object ID list.
2. Computes which IDs are missing locally.
3. Fetches each missing object by ID.
4. Verifies schema, ID, and signature.
5. Stores valid objects locally.

Invalid objects are rejected.

## Push Behavior

When a new object is stored locally, Beep may push it to configured targets. The
receiving node verifies the object before storing it.

Private room objects, events, and messages are not auto-pushed to general peers
or relays. That reduces accidental private-room existence leaks during normal
replication. It is not a full privacy model: production private rooms still need
encrypted room metadata or an access-aware sync protocol.

## Abuse Controls

The node applies basic public POST guardrails:

```text
BEEP_MAX_OBJECT_BYTES       default 262144
BEEP_MAX_POSTS_PER_MINUTE   default 60
```

These limits protect the local process from the simplest oversized-body and
rapid-post abuse. Public relays should still run behind infrastructure-level
rate limits, request logging, object retention caps, and abuse monitoring.

## Recovery Sync

Recovery can request specific object IDs from peers. IRO recovery uses:

```text
object_ids
peer_refs
```

Recovered objects are pinned with the `recovery` reason. Discovered IRO objects
are pinned with the `iro` reason.

## Relays

A relay is just an always-on node with a stable public URL. It is useful only for
objects it has received through sync. See [relay-setup.md](relay-setup.md).

## Limitations

- Sync currently uses inventory-style scans rather than delta negotiation.
- Availability depends on configured peers and relays being reachable.
- Metadata is visible to peers that receive replicated objects.
- The in-process rate limiter is not a durable peer reputation system.
