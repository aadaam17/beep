# Beep Relay Setup Guide

This guide shows how to run a Beep relay in real life.

## What A Relay Is

A relay is not a special admin account.

It is just a Beep node that is:

- always on
- reachable on a stable public URL
- used by other nodes for discovery and sync

Identity still belongs to the user's pubkey. The relay only helps nodes find and exchange objects.

## What Users Do With It

Once a relay is running publicly, users can add it with:

```text
beep relay add https://relay.example.net
```

They can then use:

```text
beep connect bob#abcdef
```

If the relay knows Bob's profile and presence objects, it can help resolve and sync that identity.

## Recommended Deployment Shape

The easiest practical setup is:

1. rent a small VPS
2. point a domain or subdomain at it
3. run the Beep node on localhost
4. expose it through Nginx or Caddy
5. enable HTTPS
6. keep it alive with `systemd`

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

Clone the Beep project on the server and install its dependencies.

Then run the node server on localhost, for example:

```text
python -m network.node --host 127.0.0.1 --port 8000 --quiet
```

This makes the Beep node reachable locally on:

```text
http://127.0.0.1:8000
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

## Step 6: Keep The Relay Running

Use a `systemd` service so the node starts on boot and restarts on failure.

### Example Service

```ini
[Unit]
Description=Beep Relay Node
After=network.target

[Service]
WorkingDirectory=/opt/beep
ExecStart=/usr/bin/python3 -m network.node --host 127.0.0.1 --port 8000 --quiet
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
beep relay policy
beep relay policy set enabled on
beep relay policy set strategy prefer-direct
beep relay policy set strategy direct-only
beep relay policy set strategy relay-first
beep relay policy set autostart on
beep relay policy set presence-ttl 86400
beep relay policy set presence-refresh 900
beep relay policy set public-endpoint https://relay.example.net
```

### Strategy Meanings

- `prefer-direct`
  - try direct peers first, then relays
- `direct-only`
  - ignore relays entirely
- `relay-first`
  - prefer relay-assisted discovery and sync before direct peers

## Important Current Limitation

Presence publication can now advertise a configured public endpoint instead of the local runtime URL. For a truly public relay or public self-hosted node, set that explicitly:

```text
beep relay policy set public-endpoint https://relay.example.net
```

Clear it later with:

```text
beep relay policy set public-endpoint clear
```

That means the most reliable public deployment model is:

- stable domain
- reverse proxy
- always-on node
- users add that public URL explicitly
