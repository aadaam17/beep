# Beep Configuration

Beep can load an optional TOML config file for developer and relay-operator
settings that are inconvenient to repeat through commands or the Textual UI.

Supported locations, in order:

```text
BEEP_CONFIG
./beep.toml
./config.toml
~/.config/beep/config.toml
~/.beep/config.toml
```

If a config file is present and valid, its values override saved network policy
at runtime. CLI policy commands still update `~/.beep/network_policy.json`, but
the TOML file remains the operator override while it exists.

## Commands

```text
beep config show
beep config path
beep config validate
```

## Example

```toml
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
peer_auth_token = ""

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
