# Security Model

Beep uses cryptographic identity and encrypted message envelopes, but it is
alpha software. This document describes the intended security boundaries and
known limitations.

## Identity

The protocol identity is the Ed25519 signing public key. Usernames are aliases
that can collide or change in local knowledge. When precision matters, use a
handle or public key, not only a username.

Fresh users are deterministic by default:

```text
signing: seed-ed25519-v1
encryption: seed-x25519-v1
```

Legacy RSA key material may exist for older histories. It should be treated as
compatibility state.

## Authenticity

Every object is signed. A node accepts an object only after checking:

- required envelope fields
- type-specific schema
- content-derived object ID
- Ed25519 signature

This protects object authorship and tamper detection. It does not prove that a
human-readable username belongs to a particular person outside the local trust
model.

## Confidentiality

Direct messages and room messages use encrypted envelopes. The current live
scheme is:

```text
x25519-aesgcm-v1
```

Encrypted objects still expose their outer envelope and metadata needed for
sync, routing, verification, and room reconstruction. Relays and peers can see
object IDs, authors, timestamps, object types, and non-encrypted metadata.

## Relays

A relay is not trusted with identity ownership. It can:

- store and serve objects it has received
- help nodes discover profiles and presence
- help peers exchange object inventories

A relay cannot forge valid objects without the author's signing key. A relay can
withhold objects, go offline, serve stale data, or observe metadata.

## Recovery

Recovery depends on the root seed, IRO objects, and reachable peers or relays
that still have the referenced objects.

Mnemonic recovery can recreate deterministic signing and encryption identity
from the seed, then use the IRO recovery envelope to rebuild local state.

Recovery risks:

- losing the mnemonic or backup password can make recovery impossible
- unreachable peers may prevent full object recovery
- old legacy RSA history requires preserved legacy RSA material
- a stale IRO may not reference the newest objects

## Local Storage

Local state is stored under `~/.beep/`. Files on disk are not all encrypted at
rest. Backup files are encrypted, but normal local runtime state depends on the
host machine's filesystem protections.

Do not use Beep for high-risk communications or irreplaceable data yet.

## Moderation and Rooms

Room permissions are enforced by replaying signed room events. Private rooms are
visible in the UI only to the owner, members, and invited users, but replicated
room objects may still exist on a node that synced them.

Private room messages are encrypted for current room recipients. Invited users
must join before sending messages.

## Current Limitations

- The protocol is not finalized.
- Metadata privacy is limited.
- Relay trust is availability-oriented, not privacy-oriented.
- There is no global identity authority.
- Object retention depends on local policy and peer availability.
