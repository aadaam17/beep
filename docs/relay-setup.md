# Beep Relay Setup Guide

This guide shows how to run a public Beep relay node for discovery and object
sync.

## What A Relay Is

A relay is not a special admin account.

It is just a Beep node that is:

- always on
- reachable on a stable public URL
- used by other nodes for discovery and sync

Identity still belongs to the user's pubkey. The relay only helps nodes find and
exchange objects that have been replicated to it.

## What Users Do With It

Once a relay is running publicly, users can add it with either command:

```text
beep relay add https://relay.example.net
beep network setup --relay https://relay.example.net
```

They can then use:

```text
beep connect bob#abcdef
```

If the relay knows Bob's profile and presence objects, it can help resolve and
sync that identity.

## Recommended Deployment Shape

The easiest practical setup is:

1. rent a small VPS
2. point a domain or subdomain at it
3. install Beep with the server dependencies
4. run the Beep node on localhost
5. expose it through Nginx or Caddy
6. enable HTTPS
7. keep it alive with `systemd`

Example final public URL:

```text
https://relay.example.net
```

## Step 1: Get A Public Server

Use any small Ubuntu VPS.

Examples:

- DigitalOcean
- Hetzner
- Linode
- AWS Lightsail

You want:

- a public IP
- stable uptime
- SSH access

## Step 2: Point DNS At The Server

Create an `A` record such as:

```text
relay.example.net -> 203.0.113.10
```

Wait for DNS to propagate.

## Step 3: Install And Run Beep

Clone the Beep project on the server and install the server dependencies:

```text
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[server]"
```

Then run the node server on localhost, for example:

```text
python -m network.node --host 127.0.0.1 --port 8000 --quiet
```

This makes the Beep node reachable locally on:

```text
http://127.0.0.1:8000
```

You can confirm the local node responds with:

```text
curl http://127.0.0.1:8000/health
```

## Step 4: Put A Reverse Proxy In Front

Use Nginx or Caddy to expose the local node publicly.

The desired traffic flow is:

```text
internet
  -> https://relay.example.net
  -> reverse proxy
  -> http://127.0.0.1:8000
```

### Example Nginx Site

```nginx
server {
    listen 80;
    server_name relay.example.net;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Step 5: Enable HTTPS

Use Let's Encrypt with Nginx or Caddy.

That gives users a stable HTTPS endpoint like:

```text
https://relay.example.net
```

After HTTPS is enabled, verify the public endpoint:

```text
curl https://relay.example.net/health
```

## Step 6: Keep The Relay Running

Use a `systemd` service so the node starts on boot and restarts on failure.

### Example Service

```ini
[Unit]
Description=Beep Relay Node
After=network.target

[Service]
WorkingDirectory=/opt/beep
ExecStart=/opt/beep/.venv/bin/python -m network.node --host 127.0.0.1 --port 8000 --quiet
Restart=always
RestartSec=5
User=beep

[Install]
WantedBy=multi-user.target
```

Then:

```text
sudo systemctl daemon-reload
sudo systemctl enable --now beep-relay
```

Check the service logs with:

```text
sudo journalctl -u beep-relay -f
```

## How Users Discover Each Other Through A Relay

Users do not need a special relay identity.

Instead:

1. a user syncs through the relay
2. their profile objects replicate there
3. their presence objects replicate there
4. other users ask the relay to resolve a handle
5. the relay answers from the objects it already knows

That means a relay is:

- a sync hub
- a discovery helper
- a stable public endpoint

It is not:

- the owner of anyone's account
- a special social user
- a central identity authority

## Manual Peers Still Matter

Relays do not replace direct peer URLs.

Direct peers are still useful for:

- same-Wi-Fi use
- self-hosted direct peering
- private groups
- testing
- users who do not want relay assistance

Manual peer add still works the normal way:

```text
beep peer add http://192.168.1.50:8000
```

## Relay Policy Commands

Beep now includes policy controls for relay behavior:

```text
beep network status
beep network check
beep node status
beep node enable
beep relay policy
beep relay policy set enabled on
beep relay policy set strategy prefer-direct
beep relay policy set strategy direct-only
beep relay policy set strategy relay-first
beep relay policy set presence-ttl 86400
beep relay policy set presence-refresh 900
beep relay policy set public-endpoint https://relay.example.net
beep relay policy set public-endpoint clear
beep relay policy set max-object-bytes 262144
beep relay policy set max-posts-per-minute 60
beep relay policy set max-objects-per-author 10000
beep relay policy set max-objects-per-ip 20000
beep relay policy set retention-limit 50000
beep relay policy set relay-only on
beep relay policy set deny-author <pubkey>
beep relay policy set allow-author <pubkey>
beep relay policy set deny-ip <ip>
beep relay policy set allow-ip <ip>
beep relay policy set peer-auth on
beep relay policy set peer-token <shared-secret>
```

### Strategy Meanings

- `prefer-direct`
  - try direct peers first, then relays
- `direct-only`
  - ignore relays entirely
- `relay-first`
  - prefer relay-assisted discovery and sync before direct peers

## Public Endpoint Policy

Presence publication can advertise a configured public endpoint instead of the
local runtime URL. Set this on a relay or self-hosted public node when other
users should discover that public URL as your reachable endpoint:

```text
beep relay policy set public-endpoint https://relay.example.net
```

Clear it later with:

```text
beep relay policy set public-endpoint clear
```

Run this after setting or changing the public endpoint:

```text
beep network check
```

The check probes `/health`, reports whether the endpoint is reachable, and shows
object count plus relay-only mode when the node exposes that information.

## Relay Safety Policy

Public relays should set explicit quotas before accepting broad traffic:

```text
beep relay policy set max-object-bytes 262144
beep relay policy set max-posts-per-minute 60
beep relay policy set max-objects-per-author 10000
beep relay policy set max-objects-per-ip 20000
beep relay policy set retention-limit 50000
```

When the retention limit is reached, the node tries local pruning before
rejecting new objects. Denylist controls are available for obvious abuse:

```text
beep relay policy set deny-author <pubkey>
beep relay policy set deny-ip <ip>
```

Use relay-only mode for a relay that should serve sync traffic without
publishing the operator's own local presence:

```text
beep relay policy set relay-only on
```

## Private Relay Mode

For private networks, enable shared-token peer authentication:

```text
beep relay policy set peer-auth on
beep relay policy set peer-token <shared-secret>
```

Peers with the same policy token send `X-Beep-Peer-Token` on sync and discovery
requests. `/health` remains public so operators can check reachability.

That means the most reliable public deployment model is:

- stable domain
- reverse proxy
- always-on node
- users add that public URL explicitly

## Operational Notes

- A relay is only useful for objects it has received through sync.
- Keep the relay process online and reachable over HTTPS.
- Use `beep network check` from a client node after adding the relay.
- Direct peers and relays can be used together; the active strategy decides the
  order.
