# Beep Configuration

Beep can load an optional TOML config file for developer and relay-operator
settings that are inconvenient to repeat through commands or the Textual UI.

## Precedence

Config locations are checked in this order:

```text
BEEP_CONFIG
./beep.toml
./config.toml
~/.config/beep/config.toml
~/.beep/config.toml
```

Runtime order is:

1. Built-in defaults
2. Saved JSON policy/state files
3. Valid TOML config overrides

CLI policy commands still update `~/.beep/network_policy.json`. If a TOML file
sets the same field, the TOML value remains the runtime override until removed.
Config-defined peers and relays are merged at runtime and are not written back
to `peers.json` or `relays.json`.

## Commands

```text
beep config init
beep config init ~/.config/beep/config.toml
beep config show
beep config effective
beep config path
beep config validate
```

`show` reports the active file and sections. `effective` also prints redacted
runtime overrides, config peers, and config relays. `validate` reports errors
and warnings without applying any changes.

## Example

```toml
version = 1

[node]
enabled = false
relay_only = false

[network]
relay_enabled = true
strategy = "prefer-direct"
public_endpoint = "https://relay.example.net"
presence_ttl_seconds = 86400
presence_refresh_seconds = 900
peer_auth_required = false
peer_auth_token_env = "BEEP_PEER_AUTH_TOKEN"

[relay]
max_object_bytes = 262144
max_posts_per_minute = 60
max_objects_per_author = 10000
max_objects_per_ip = 20000
retention_limit = 50000
relay_only = false
denylisted_authors = []
denylisted_ips = []

[peers]
urls = [
  "http://127.0.0.1:8001"
]

[relays]
urls = [
  "https://relay.example.net"
]
```

`peers` and `relays` can also be simple top-level arrays:

```toml
peers = ["http://127.0.0.1:8001"]
relays = ["https://relay.example.net"]
```

## Secrets

Prefer environment-backed secrets:

```toml
[network]
peer_auth_required = true
peer_auth_token_env = "BEEP_PEER_AUTH_TOKEN"
```

Then start Beep with the environment variable set. A literal
`peer_auth_token = "..."` is still supported, but `beep config effective`
redacts it.

## Diagnostics

Unknown sections and keys produce warnings and are ignored. Invalid values, bad
TOML, and unsupported config versions produce errors. When errors exist, Beep
does not apply config overrides.
