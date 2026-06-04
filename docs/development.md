# Development

This guide covers local setup, tests, packaging, and codebase orientation.

## Setup

Recommended development install:

```bash
python -m venv venv
python -m pip install --upgrade pip
python -m pip install -e ".[server,ui,dev]"
```

Alternative dependency install:

```bash
python -m pip install -r requirements.txt
```

The project requires Python 3.11 or newer.

## Running Beep

Classic command shell:

```bash
beep
```

Textual UI:

```bash
beep shell
```

Manual node runtime:

```bash
python -m network.node --host 0.0.0.0 --port 8000
```

Client mode is the default. Beep checks basic device capacity before prompting
for node mode, including mobile/Termux-like environments, CPU count, memory,
free storage, Python version, and local socket binding. Optional hosting can be
enabled manually with:

```bash
beep node enable
beep node status
beep node disable
```

If background startup fails on Termux or another slower device, run
`beep node status` and inspect the reported node log. The startup wait can be
increased with `BEEP_NODE_STARTUP_TIMEOUT=<seconds>`.

## Tests

Run all tests:

```bash
python -m unittest discover -s tests
```

Run a specific test module:

```bash
python -m unittest tests.test_room_commands
```

## Packaging

Build distributions:

```bash
python -m build
```

Validate distributions:

```bash
python -m twine check dist/*
```

The package name is:

```text
beep-cli
```

The console script is:

```text
beep = cli:main
```

## Project Layout

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
docs/               Documentation
```

## Development Notes

- Keep protocol behavior documented in `docs/protocol.md`.
- Keep relay deployment notes in `docs/relay-setup.md`.
- Preserve backward compatibility for legacy RSA history when touching recovery
  or encryption code.
- Objects accepted from peers must continue to pass schema, ID, and signature
  verification.
- Avoid changing storage paths without a migration plan.
