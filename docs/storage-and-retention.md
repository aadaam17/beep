# Storage and Retention

Beep is local-first. Runtime state and replicated objects are stored under the
user's home directory.

## Storage Layout

Important paths:

```text
~/.beep/session.json
~/.beep/network_policy.json
~/.beep/beep_users.json
~/.beep/beep_storage/
~/.beep/beep_storage/objects/
~/.beep/beep_storage/pins.json
```

Object files live in:

```text
~/.beep/beep_storage/objects/<object_id>.json
```

Each object is verified before it is written.

## Pins

Pins are stored in:

```text
~/.beep/beep_storage/pins.json
```

Pin reasons currently include:

```text
retain
iro
recovery
```

Pinned objects are protected from pruning.

## Retention Reasons

The retention policy keeps objects that are important to the local user. Current
retention reasons include:

```text
retain
iro
recovery
identity
authored
following
chat_participant
room_participant
```

Beep retains:

- explicitly pinned objects
- local profile and IRO objects
- objects authored by local identities
- supported objects authored by followed users
- direct-message objects related to local users
- room objects, events, and messages related to local users
- recovery-pinned objects fetched from IRO recovery

Objects with no retention reason are considered prunable.

## Commands

Show retention status:

```text
beep storage status
beep storage status --reason <reason>
```

Inspect why one object is retained:

```text
beep storage inspect <object_id>
```

Dry-run pruning:

```text
beep storage prune
```

Apply pruning:

```text
beep storage prune --apply
```

## Pruning Behavior

`storage prune` is a dry run by default. With `--apply`, Beep deletes objects
that have no retention reason. It also removes stale pin entries for files that
no longer exist.

Pruning does not ask peers for replacement copies. If an object is pruned and no
peer or relay still has it, it may be difficult or impossible to recover.

## Recovery-Critical Objects

IRO and recovery-fetched objects should remain pinned. These objects are used to
rebuild identity state and recover indexed history from peers.
