# Recovery

Beep supports encrypted backup files, mnemonic recovery, and IRO-guided recovery
from peers.

## Backup Files

Create an encrypted backup:

```text
beep backup create --file backup.enc
```

Import an encrypted backup:

```text
beep backup import --file backup.enc
beep restore --file backup.enc
```

Backup files use:

```text
format: beep-backup-v1
kdf: pbkdf2-sha256
cipher: aes-256-gcm
```

Encrypted backup payloads contain:

- local user record
- root seed
- deterministic signing private key
- IRO ID and decrypted IRO payload when available
- referenced objects that are available locally
- legacy RSA material only when present

## Mnemonic Recovery

Create a mnemonic:

```text
beep backup create --mnemonic
```

Restore from a mnemonic:

```text
beep restore --mnemonic "<phrase>" -p <password>
```

Mnemonic recovery:

1. Converts the phrase back into the root seed.
2. Re-derives the deterministic Ed25519 signing identity.
3. Finds the latest IRO for that public key locally or from peers.
4. Decrypts the IRO recovery envelope with the seed-derived recovery key.
5. Rebuilds local signing and exchange key state.
6. Restores optional legacy RSA state if present.
7. Saves a local user record and session.

## Recover Missing Objects

After identity recovery, fetch missing IRO-indexed objects:

```text
beep restore recover
```

This uses:

```text
iro_payload.object_ids
iro_payload.peer_refs
configured peers
```

Recovered objects are pinned with the `recovery` reason. IRO objects are pinned
with the `iro` reason.

## Requirements for Successful Recovery

For complete recovery, at least one configured peer or relay should still have:

- the latest IRO object
- objects referenced by the IRO
- profile and presence data needed for discovery

If no reachable peer has the latest IRO or referenced objects, recovery may be
partial.

## Legacy RSA

New identities do not depend on RSA. Legacy RSA material is restored only when it
exists in a backup or IRO payload. It is needed only for older RSA-encrypted
history.
