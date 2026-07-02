# Beep Private Meaning Layer

The Private Meaning Layer (PML) is an optional local text interpreter for direct
messages. It runs before encryption when sending and after decryption when
reading.

PML is not a replacement for encryption. It is an extra semantic layer: even if
someone sees decrypted text like `X91 at T77`, they still need the local cipher
profile to understand the intended meaning.

## Storage

Cipher profiles live locally:

```text
~/.beep/ciphers/
```

Examples:

```text
default.json
family.json
ops.json
ops.v2.json
```

## Commands

```text
beep cipher create ops
beep cipher set ops "meet tonight" X91
beep cipher set ops "safehouse" T77
beep cipher show ops
beep cipher export ops
beep cipher import ops.beepcipher
beep cipher import ops.beepcipher --as ops_shared
beep cipher rotate ops
beep cipher revoke ops
```

## Sending

Inside a chat:

```text
beep say "meet tonight at safehouse" --cipher ops
```

One-shot send:

```text
beep chat bob "meet tonight at safehouse" --cipher ops
```

Beep transforms the message first:

```text
meet tonight at safehouse
X91 at T77
```

Then it encrypts and signs the DM object. The DM metadata records:

```text
pml_version
cipher_profile
cipher_version
cipher_fingerprint
```

The profile name and fingerprint are metadata. The mapping itself is never
replicated through normal message sync.

## Receiving

When reading a DM, Beep decrypts the message and then tries to load the matching
local cipher profile/version. If the profile exists, it decodes the text. If the
profile is missing, Beep shows the decrypted encoded text as-is.

## Sharing Profiles

The initial sharing model is out-of-band:

```text
beep cipher export ops
```

Send the `.beepcipher` file by USB, Bluetooth, Signal, email, or another channel.
The receiver imports it:

```text
beep cipher import ~/Downloads/ops.beepcipher
```

Exports include a SHA-256 fingerprint over profile, version, and mapping. Import
rejects files with fingerprint mismatches.

## Rotation And Revocation

Rotate profiles to reduce long-term pattern analysis:

```text
beep cipher rotate ops
```

This creates `ops.v2.json` with copied mappings. New DMs record
`cipher_version = 2`.

If a profile leaks:

```text
beep cipher revoke ops
```

Revoked profiles are blocked for future sends. Old received messages can still
be decoded when their versioned profile remains available locally.
