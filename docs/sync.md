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
