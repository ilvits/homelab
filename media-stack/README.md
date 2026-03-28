# Media Stack

Jellyfin media server with the full *arr suite, routed through a Gluetun WireGuard VPN gateway.

## Architecture

Containers are split into two groups based on network access:

**Behind VPN (`network_mode: service:gluetun`)** — share Gluetun's network namespace, all traffic exits through WireGuard:
- Prowlarr — indexer manager
- Sonarr — TV series automation
- Radarr — movie automation
- Lidarr — music automation
- Bazarr — subtitle management
- FlareSolverr — Cloudflare bypass for Prowlarr
- Jellyseerr — content request UI

**Direct network access (`media` bridge)** — no VPN, communicate with VPN containers via Gluetun's exposed ports:
- Jellyfin — media server
- qBittorrent — torrent client

## Services & Ports

| Container    | Port       | Notes            |
|--------------|------------|------------------|
| Jellyfin     | 8096, 8920 | Media server UI  |
| qBittorrent  | 8080       | Web UI; 6881 for torrents |
| Prowlarr     | 9696       | Via Gluetun      |
| Sonarr       | 8989       | Via Gluetun      |
| Radarr       | 7878       | Via Gluetun      |
| Lidarr       | 8686       | Via Gluetun      |
| Bazarr       | 6767       | Via Gluetun      |
| FlareSolverr | 8191       | Via Gluetun      |
| Jellyseerr   | 5055       | Via Gluetun      |

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable                   | Description                                                  |
|----------------------------|--------------------------------------------------------------|
| `TZ`                       | Timezone (e.g. `Europe/Moscow`)                              |
| `PUID` / `PGID`            | User/group ID for linuxserver containers                     |
| `APPDATA`                  | Path to container config directories                         |
| `MEDIAFILES`               | Path to media library root                                   |
| `WG_PRIVATE_KEY`           | WireGuard client private key                                 |
| `WG_ADDRESS`               | WireGuard client IP (e.g. `10.8.0.2/32`)                    |
| `WG_PUBLIC_KEY`            | WireGuard server public key                                  |
| `WG_ENDPOINT_IP`           | WireGuard server IP                                          |
| `WG_ENDPOINT_PORT`         | WireGuard server port (default: `51820`)                     |
| `WG_DNS`                   | DNS server used inside VPN tunnel                            |
| `FIREWALL_INPUT_PORTS`     | Ports allowed inbound through Gluetun firewall               |
| `FIREWALL_OUTBOUND_SUBNETS`| Subnets reachable without going through VPN                  |

## Usage

```bash
# Start the stack
docker compose up -d

# Restart only Gluetun and Lidarr (e.g. after config change)
docker compose up -d --force-recreate gluetun lidarr

# Verify VPN is active for a container behind Gluetun
docker exec lidarr curl -s https://ipinfo.io/ip

# View logs
docker compose logs -f gluetun
```

## Startup Order

Gluetun must be healthy before any VPN-dependent container starts. This is enforced
via `depends_on` with `condition: service_healthy`. Download clients (Sonarr, Radarr,
Lidarr, Bazarr) additionally wait for qBittorrent to be healthy.

## Notes

- `.env` is excluded from Git via `.gitignore` — never commit real keys
- Gluetun healthcheck hits `https://ipinfo.io/ip` to confirm VPN connectivity
- `FIREWALL_OUTBOUND_SUBNETS` includes `192.168.10.0/24` so VPN containers can
  reach local LAN services (NPM, Authentik, etc.)
