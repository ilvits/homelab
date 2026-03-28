# Homelab

Personal homelab running on **Unraid** with 22 stacks, managed via Docker Compose.

## Hardware

| Component | Spec |
|-----------|------|
| **CPU** | Intel N100 |
| **RAM** | 32 GB |
| **Cache (appdata)** | SSD |
| **Array (media/data)** | HDD |
| **OS** | Unraid |
| **Additional** | Raspberry Pi 3 & 4 (Pi-hole DNS), MikroTik hEX RB750GR3 (router / WireGuard VPN) |

## Structure

All stacks live in `/mnt/user/appdata/compose/`, each in its own subdirectory:

```
compose/
├── apprise-api/
├── authentik/
├── beszel/
├── cloudflared/
├── duplicati/
├── fairybrains/
├── filebrowser/
├── frigate/
├── homepage/
├── icloudpd-watchdog/
├── immich/
├── joplin/
├── mealie/
├── media-stack/
├── navidrome/
├── npm/
├── ntfy/
├── scripts/
├── seafile/
├── sftpgo/
├── uptime-kuma/
├── vaultwarden/
└── vikunja/
```

Each stack has its own `docker-compose.yml` and `.env` file (excluded from git via `.gitignore`).
Sensitive values are never committed — see `.env.example` files for required variables.

## Stacks

### Auth & Access

| Stack | Description |
|-------|-------------|
| [authentik](./authentik/) | SSO / Identity Provider — centralised auth for all services |
| [npm](./npm/) | Nginx Proxy Manager — reverse proxy with SSL termination |
| [cloudflared](./cloudflared/) | Cloudflare Tunnel — secure external access without open ports |
| [vaultwarden](./vaultwarden/) | Self-hosted Bitwarden-compatible password manager |

### Media & Files

| Stack | Description |
|-------|-------------|
| [media-stack](./media-stack/) | Full *arr suite — Jellyfin, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Jellyseerr, qBittorrent, FlareSolverr (all except Jellyfin behind Gluetun VPN) |
| [immich](./immich/) | Photo & video backup (Google Photos alternative), with ML support |
| [seafile](./seafile/) | File sync & share (Dropbox alternative) |
| [navidrome](./navidrome/) | Music streaming server (Spotify alternative) |
| [icloudpd-watchdog](./icloudpd-watchdog/) | iCloud photo sync with Telegram bot watchdog |
| [filebrowser](./filebrowser/) | Web-based file manager |
| [sftpgo](./sftpgo/) | SFTP / WebDAV server for secure file transfers |

### Monitoring & Notifications

| Stack | Description |
|-------|-------------|
| [beszel](./beszel/) | Lightweight server & container resource monitoring |
| [uptime-kuma](./uptime-kuma/) | Service uptime monitoring with alerting |
| [apprise-api](./apprise-api/) | Multi-platform notification gateway (Telegram alerts) |
| [ntfy](./ntfy/) | Self-hosted push notification service |
| [duplicati](./duplicati/) | Encrypted backups — Vaultwarden → VPS (SFTP) + Google Drive |
| [frigate](./frigate/) | NVR with real-time object detection — 9 cameras, Coral TPU |

### Productivity

| Stack | Description |
|-------|-------------|
| [vikunja](./vikunja/) | Self-hosted task manager (Todoist alternative) |
| [joplin](./joplin/) | Note-taking with sync server (Evernote alternative) |
| [mealie](./mealie/) | Recipe manager & meal planner |
| [homepage](./homepage/) | Customisable dashboard for all services |

### Other

| Stack | Description |
|-------|-------------|
| [fairybrains](./fairybrains/) | Personal website (Node.js), exposed via Cloudflare Tunnel |

## Usage

```bash
# Start a stack
cd /mnt/user/appdata/compose/<stack-name>
docker compose up -d

# Stop a stack
docker compose down

# View logs
docker compose logs -f

# Update images
docker compose pull && docker compose up -d

# Restart a single container
docker compose restart <container-name>
```

## Networking

- **Reverse proxy**: Nginx Proxy Manager with SSL (Let's Encrypt)
- **External access**: Cloudflare Tunnel — no ports exposed to the internet
- **VPN**: WireGuard + AmneziaWG on VPS, managed via WGDashboard
- **macvlan**: NPM, Seafile, Frigate use dedicated LAN IPs via `br0` macvlan
- **DNS**: Pi-hole on Raspberry Pi 4 (primary) + Raspberry Pi 3 (backup)

## Security

- All secrets in `.env` files, excluded from git via `.gitignore`
- External access via Cloudflare Tunnel only
- SSO via Authentik for supported services
- Encrypted backups via Duplicati
- VPN-only access for sensitive services (Portainer, internal dashboards)

## Notes

- `TZ` is intentionally omitted from Authentik compose — setting it breaks OAuth/SAML
- Seafile uses `COMPOSE_FILE` env var for multi-file compose setup
- Vikunja requires `config.yml` with `service.publicurl` — env vars alone are insufficient
- `media-stack`: all *arr apps and Lidarr route through Gluetun (WireGuard VPN gateway)
- Monitoring scripts in `scripts/` run on the Unraid host via cron (User Scripts plugin)
