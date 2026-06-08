# Beep Data Model

This document records the protocol-level data model rules that should stay
stable across CLI, node, storage, and UI code.

## Versioned Schemas

Object type schemas live outside Python code in:

```text
core/protocol_schemas/v1/object-types.schema.json
```

The schema document is versioned with:

```text
protocol: beep-object-v1
protocol_version: 1
```

Runtime validation loads this file from `core.schemas`. The Python validator
intentionally implements only the JSON Schema subset used by the protocol file:

- required metadata fields
- primitive JSON types
- enums and constants
- reusable `$ref` definitions
- conditional required fields for room events
- any-of-required groups for profile keys and IRO payload envelopes

Incompatible schema semantics require a protocol version bump. Additive optional
metadata can remain on the current version when old nodes can safely ignore it.

## Conflict Rules

Beep objects are immutable, so conflicts are resolved by object family instead
of overwriting objects in place.

| Object family | Conflict rule |
| --- | --- |
| `profile` | Select latest profile by `(timestamp, id)` for the same author. Profiles must be signed by the identity author. |
| `follow` | Replay follow/unfollow events ordered by `(timestamp, id)` per `(author, target)`. The latest action controls the edge. |
| `presence` | Select the freshest unexpired presence by `(timestamp, id)` for the same author. Stale presence remains historical only. |
| `room` | The room creation object defines room identity. Duplicate room IDs are ignored unless signed by the same owner and accepted by migration policy. |
| `room_event` | Replay authorized room events ordered by `(timestamp, id)`. Events from unauthorized authors are ignored during state rebuild. |
| `iro` | Select the highest decryptable payload version, then newest `(timestamp, id)`, for the expected owner key. |

Tie-breaking by object ID is deterministic and avoids depending on filesystem
order or peer arrival order.

## Public vs Private Objects

Retention and sync policy classify objects before deciding whether to relay or
prune them.

| Visibility | Object families | Policy |
| --- | --- | --- |
| `public` | posts, comments, shares, quotes, profiles, key revocations, tombstones, presence, follows, public rooms, public room events | General sync and relay eligible. Disposable unless pinned, local-authored, identity-related, or from followed authors. |
| `public_encrypted` | IROs | General sync eligible because metadata is public and payload is encrypted. Retained for local identity/recovery or followed-author recovery policy. |
| `private_encrypted` | DMs, room messages, private rooms, encrypted/private room events | Not pushed to general peers or relays. Retained only when a local user authored it, can decrypt it, owns the room, was invited, or participates in the room. |

This split reduces accidental leakage and prevents public-relay retention limits
from treating private encrypted material as ordinary public feed data.
