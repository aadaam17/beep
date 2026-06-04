# Beep Protocol

This document describes the current Beep object protocol as implemented in the
codebase. The protocol is alpha and may change.

## Object Envelope

Every stored Beep object uses the same outer envelope:

```text
type        object family
author      Ed25519 signing public key, hex encoded
content     object body or encrypted placeholder text
timestamp   Unix timestamp
meta        type-specific JSON object
id          SHA-256 hash of the canonical unsigned object
signature   Ed25519 signature over the canonical unsigned object
```

The canonical unsigned payload includes:

```text
type
author
content
timestamp
meta
```

The `id` is the SHA-256 hash of that canonical JSON payload with sorted keys and
compact separators. The signature is an Ed25519 signature over the same
canonical payload. The signature itself is not part of the object ID.

## Protocol Version

New objects include signed protocol metadata:

```text
meta.protocol         beep-object-v1
meta.protocol_version 1
```

`core/protocol.py` defines the supported protocol versions. Version metadata is
part of the canonical payload, so changing it changes the object ID and
signature. Legacy objects without explicit version metadata remain accepted, but
future objects with unknown protocol names or unsupported versions are rejected.

Migration policy:

- Add new optional fields without changing `protocol_version` when old nodes can
  safely ignore them.
- Increment `protocol_version` for incompatible envelope, hashing, signing, or
  semantic schema changes.
- Keep compatibility tests for legacy unversioned objects and all supported
  protocol versions.

## Verification

Before an object is stored or accepted from a peer, Beep verifies:

1. Required fields are present.
2. The object type-specific schema is valid.
3. Explicit protocol metadata is supported.
4. The object ID matches the canonical unsigned payload.
5. The signature verifies against the `author` public key.

Objects that fail verification are rejected.

## Object Types

Current object families:

```text
post
comment
share
quote
profile
presence
iro
follow
chat
dm
room
room_event
room_message
```

### Social Objects

`post` stores plain authored text.

`comment` requires:

```text
meta.parent_id
```

`share` and `quote` require:

```text
meta.shared_from
```

### Profile Objects

`profile` requires:

```text
meta.username
```

It must publish either deterministic exchange key metadata or legacy RSA
metadata. New identities publish deterministic X25519 metadata.

### Presence Objects

`presence` requires:

```text
meta.username
meta.endpoint
meta.reachable_via
```

Optional presence metadata includes:

```text
meta.ttl
meta.relay_hints
```

Presence is used for discovery and endpoint freshness. It is not an identity
authority.

### Follow Objects

`follow` requires:

```text
meta.action
meta.target
```

Supported actions are:

```text
follow
unfollow
```

### Direct Message Objects

`chat` identifies a direct chat thread.

`dm` requires:

```text
meta.chat
meta.encrypted
```

The encrypted envelope stores ciphertext and recipient key slots.

### Room Objects

`room` requires:

```text
meta.room_id
meta.private
meta.owner_pubkey
meta.key_epoch
```

Optional:

```text
meta.ttl
```

Room state is reconstructed by replaying `room_event` objects for the room.

`room_event` requires:

```text
meta.room
meta.action
```

Supported actions:

```text
invite
join
leave
mod
unmod
mute
unmute
kick
dissolve
```

Targeted actions include:

```text
meta.target_pubkey
```

Invites also require:

```text
meta.target_key_id
meta.encrypted
```

`room_message` requires:

```text
meta.room
meta.encrypted
```

## Identity Root Object

The Identity Root Object (IRO) is a signed object of type `iro` that stores a
recoverable encrypted index for an identity.

Required metadata:

```text
meta.owner_pubkey
meta.version
meta.payload_kind = iro_index
```

At least one encrypted payload envelope must be present:

```text
meta.encrypted
meta.recovery_encrypted
```

Optional legacy compatibility:

```text
meta.legacy_encrypted
```

The decrypted IRO payload tracks:

```text
version
username
owner_pubkey
object_ids
post_ids
chat_ids
room_ids
peer_refs
legacy_rsa_private_pem
legacy_rsa_public_pem
```

Legacy RSA fields are optional and exist only when needed for older imported or
recovered history.

## Encryption Schemes

Current live encryption uses:

```text
x25519-aesgcm-v1
```

Seed recovery uses:

```text
seed-recovery-aes-gcm-v1
```

Legacy compatibility may use:

```text
rsa-oaep-v1
```

New live encrypted communication should use deterministic X25519 identities.
RSA is compatibility state, not the live path.
