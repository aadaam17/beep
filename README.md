# Beep

Beep is a local-first, terminal-native social network prototype built around
cryptographic identity, signed immutable objects, peer-to-peer replication, and
recoverable account ownership.

It is not a hosted platform. Beep is a Python CLI, Textual shell, local object
store, and lightweight node runtime that together form an experimental
decentralized social protocol.

## Highlights

- Deterministic Ed25519 signing identities and X25519 encryption identities
- Immutable signed objects for posts, profiles, follows, chats, rooms, presence,
  and recovery metadata
- Local-first storage under the user's home directory
- Direct peer sync and relay-assisted discovery
- Encrypted direct messages and room messages
- Identity Root Object (IRO) recovery using encrypted backup files or mnemonic
  seed recovery
- Classic command shell plus an optional Textual terminal UI
- Storage retention, pinning, inspection, and pruning commands

## Project Status

Beep is alpha software. The current codebase is suitable for local development,
protocol experimentation, and testing peer-to-peer workflows. Object schemas,
network behavior, and retention policy are implemented in code, but the protocol
is still evolving and should not be treated as a stable production standard.

## Requirements

- Python 3.11 or newer
- `cryptography`
- `requests`
- Optional server runtime: `fastapi`, `uvicorn`
- Optional Textual UI: `textual`
- Optional packaging tools: `build`, `twine`

## Installation

Recommended local development install:

```bash
python -m venv venv
python -m pip install --upgrade pip
python -m pip install -e ".[server,ui,dev]"
```

For a minimal package install, use the base editable install. This is useful for
packaging checks, but day-to-day app usage should install the server and UI
extras above.

```bash
python -m pip install -e .
```

For an isolated CLI install:

```bash
pipx install .
```

You can also install the dependency list directly:

```bash
python -m pip install -r requirements.txt
```

## Quick Start

Launch the classic persistent command shell:

```bash
beep
```

Or run it directly from the repository:

```bash
python cli.py
```

Inside the shell, commands begin with `beep`:

```text
beep register -u alice -p pass123
beep login -u alice -p pass123
beep post "hello world"
beep fyp global
```

Launch the Textual interactive shell:

```bash
beep shell
```

Direct one-shot commands are intentionally not the primary interface. If extra
arguments are passed to the installed `beep` entry point, the app starts the
persistent command shell and explains how to continue there.

## Core Concepts

### Identity

Human usernames are aliases. The protocol identity is the user's signing public
key. Beep publishes short handles in the form:

```text
username#handle
```

Fresh identities are deterministic by default:

- Signing: `seed-ed25519-v1`
- Encryption: `seed-x25519-v1`
- Legacy compatibility: optional `rsa-legacy-v1`

RSA material is retained only for imported or recovered legacy history that
still needs it. New live encrypted communication uses deterministic X25519.

### Objects

Beep stores data as signed immutable objects with this common shape:

- `type`
- `author`
- `content`
- `timestamp`
- `meta`
- `id`
- `signature`

The implemented object families include:

- `post`
- `comment`
- `share`
- `quote`
- `profile`
- `presence`
- `iro`
- `follow`
- `chat`
- `dm`
- `room`
- `room_event`
- `room_message`

Incoming objects are verified before storage. Invalid or untrusted objects are
rejected by the local store and sync layer.

### Identity Root Object

The Identity Root Object (IRO) is a signed, recoverable index owned by a user's
public key. It tracks the owner's important object IDs and recovery references:

- `owner_pubkey`
- `username`
- `object_ids`
- `post_ids`
- `chat_ids`
- `room_ids`
- `peer_refs`

IRO metadata supports multiple encrypted envelopes:

- `meta.encrypted`: live deterministic owner access with `x25519-aesgcm-v1`
- `meta.recovery_encrypted`: seed recovery with `seed-recovery-aes-gcm-v1`
- `meta.legacy_encrypted`: optional RSA compatibility with `rsa-oaep-v1`

Mnemonic recovery uses the seed recovery envelope. Legacy RSA fields are carried
only when the recovered identity actually has legacy state.

## Storage

Beep stores local state under:

```text
~/.beep/
```

Important locations include:

```text
~/.beep/session.json
~/.beep/beep_users.json
~/.beep/beep_storage/
~/.beep/beep_storage/objects/
~/.beep/beep_storage/pins.json
```

The object retention policy protects local identity objects, authored content,
followed-user objects, local chat and room history, recovery-critical objects,
and explicit pins. Disposable replicated objects can be inspected or pruned with
the storage commands.

## Command Reference

### Identity and Recovery

```text
beep register -u <username> -p <password>
beep login -u <username> -p <password>
beep logout
beep connect
beep connect <username|username#handle>
beep backup create --file <path>
beep backup create --mnemonic
beep backup import --file <path>
beep restore --file <path>
beep restore --mnemonic "<phrase>" -p <password>
beep restore recover
```

### Feed, Posts, and Profiles

```text
beep fyp global
beep fyp followed
beep fyp --live
beep next
beep hold
beep resume
beep post "content"
beep comment <object_id> "reply"
beep share <post_id>
beep quote <post_id> "text"
beep view <object_id>
beep profile
beep profile <username|username#handle>
beep profile --followers
beep profile --following
beep profile --posts
beep profile --shared
beep follow <username|username#handle>
beep unfollow <username|username#handle>
```

### Direct Messages

```text
beep chat
beep chat <username|username#handle>
beep chat <username|username#handle> --live
beep say "message"
beep read [--all | <number>]
beep exit
```

`say` sends to the active chat when the shell is in chat mode.

### Rooms

```text
beep room
beep room <name> [--private] [--ephemeral <ttl>]
beep join <name>
beep join <name> --live
beep invite <username>
beep say "message"
beep late [--all | <number>]
beep leave
beep dissolve
```

Ephemeral room TTLs accept values such as:

```text
15s
1m
1h
2d
```

Room moderation commands:

```text
beep mute <username>
beep unmute <username>
beep kick <username>
beep mod <username>
beep unmod <username>
```

### Network, Peers, and Relays

```text
beep network
beep network setup
beep network setup --relay <url>
beep network setup --peer <url>
beep network check
beep network check --live
beep peer add <url>
beep peer remove <url>
beep peer list
beep relay add <url>
beep relay remove <url>
beep relay list
beep relay policy
beep sync
beep node run [--port <port>]
```

Relay policy can be tuned from the shell:

```text
beep relay policy set enabled on
beep relay policy set strategy prefer-direct
beep relay policy set strategy direct-only
beep relay policy set strategy relay-first
beep relay policy set autostart on
beep relay policy set presence-ttl 86400
beep relay policy set presence-refresh 900
beep relay policy set public-endpoint https://relay.example.net
beep relay policy set public-endpoint clear
```

See [docs/relay-setup.md](docs/relay-setup.md) for a practical relay deployment
guide.

### Storage Retention

```text
beep storage status
beep storage status --reason <reason>
beep storage inspect <object_id>
beep storage prune
beep storage prune --apply
```

`storage prune` performs a dry run by default. Use `--apply` to delete objects
that are not retained by the local policy.

## Node API

The node runtime is a FastAPI application used for local sync, discovery, and
object exchange. Run it manually with:

```bash
python -m network.node --host 0.0.0.0 --port 8000
```

The CLI can also start a policy-controlled background node after login or
registration. The node exposes endpoints for:

- Listing object IDs
- Fetching objects by ID
- Receiving objects from peers
- Inventory exchange
- Querying objects by author or type
- Recent object listing
- Identity resolution by username or handle

## Architecture

```text
app.py              Command loop, dispatch, live mode, session refresh
cli.py              Installed entry point
commands/           User-facing command dispatchers
core/               Object model, schemas, hashing, signing, verification
crypto/             Seed, mnemonic, key, and signing helpers
models/             Lightweight domain models
network/            Node runtime, peer management, sync, discovery, reachability
node/               Runtime support helpers
storage/            Local persistence, profiles, objects, chats, rooms, recovery
ui/                 Textual application and screens
utils/              Parsing, prompting, paging, and error helpers
tests/              Unit and end-to-end coverage
docs/               Operational documentation
```

## Documentation

- [Protocol](docs/protocol.md)
- [Security model](docs/security-model.md)
- [Storage and retention](docs/storage-and-retention.md)
- [Sync](docs/sync.md)
- [Rooms](docs/rooms.md)
- [Recovery](docs/recovery.md)
- [Relay setup](docs/relay-setup.md)
- [Development](docs/development.md)

## Development

Run the test suite with:

```bash
python -m unittest discover -s tests
```

Build distributions with:

```bash
python -m build
```

Validate release artifacts with:

```bash
python -m twine check dist/*
```

The project is packaged as `beep-cli` and exposes the console script:

```text
beep = cli:main
```

## Publishing

Manual upload:

```bash
python -m twine upload dist/*
```

GitHub Actions trusted publishing is configured in:

```text
.github/workflows/publish-pypi.yml
```

## Security Notes

Beep uses cryptographic signatures and encrypted envelopes, but it is still an
alpha project. Do not use it for high-risk communications or irreplaceable data.
The code currently prioritizes local experimentation, protocol clarity, and
compatibility with prior object history.

Important current rules:

1. New identities are deterministic-only.
2. New encrypted live communication uses X25519 envelopes.
3. RSA is compatibility state, not a live dependency.
4. Objects must verify before they are stored or replicated.
5. Recovery-critical objects should remain pinned or otherwise retained.

## License

Beep is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
