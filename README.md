# Homelab

Personal homelab running on **Unraid** with 23 stacks, managed via Docker Compose.

## Hardware

| Component | Spec |
|-----------|------|
| **CPU** | Intel N100 |
| **RAM** | 32 GB |
| **Cache (appdata)** | SSD |
| **Array (media/data)** | HDD |
| **OS** | Unraid |
| **Additional** | Raspberry Pi 4B (Pi-hole primary), Raspberry Pi 3 (Pi-hole backup), MikroTik hEX RB750GR3 (router / WireGuard VPN) |

## Structure

All stacks live in `/mnt/user/appdata/compose/`, each in its own subdirectory:

```
compose/
├── apprise-api/
├── authentik/
├── beszel/
├── cloudflared/
├── dockge/
├── duplicati/
├── fairybrains/
├── filebrowser/
├── frigate/
├── homepage/
├── icloudpd-watchdog/
├── immich/
├── joplin/
├── lidarr-discovery/
├── mealie/
├── media-stack/
├── navidrome/
├── npm/
├── scripts/
├── seafile/
├── sftpgo/
├── uptime-kuma/
├── vaultwarden/
└── vikunja/
```

Each stack has its own `docker-compose.yml` (or `compose.yaml` for Dockge) and a `.env` file excluded from git.
Sensitive values are never committed — see `.env.example` files for required variables.

## Stacks

### Auth & Access

| Stack | Description |
|-------|-------------|
| [authentik](./authentik/) | SSO / Identity Provider — centralised auth for all services |
| [npm](./npm/) | Nginx Proxy Manager — reverse proxy with SSL termination, macvlan IP 192.168.10.3 |
| [cloudflared](./cloudflared/) | Cloudflare Tunnel — secure external access without open inbound ports |
| [vaultwarden](./vaultwarden/) | Self-hosted Bitwarden-compatible password manager |

### Media & Files

| Stack | Description |
|-------|-------------|
| [media-stack](./media-stack/) | Full *arr suite — Jellyfin, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Jellyseerr, qBittorrent, FlareSolverr; all traffic except Jellyfin/qBittorrent routed through Gluetun VPN |
| [immich](./immich/) | Photo & video backup (Google Photos alternative) with OpenVINO ML acceleration |
| [seafile](./seafile/) | File sync & share (Dropbox alternative), macvlan IP 192.168.10.7 |
| [navidrome](./navidrome/) | Music streaming server (Subsonic-compatible) |
| [icloudpd-watchdog](./icloudpd-watchdog/) | Automated iCloud photo sync for two accounts with Telegram bot 2FA handling |
| [filebrowser](./filebrowser/) | Web-based file manager |
| [sftpgo](./sftpgo/) | SFTP / FTP / WebDAV server |

### Monitoring & Infrastructure

| Stack | Description |
|-------|-------------|
| [beszel](./beszel/) | Lightweight host & container resource monitoring with agent |
| [uptime-kuma](./uptime-kuma/) | Service uptime monitoring with Telegram alerting |
| [apprise-api](./apprise-api/) | Unified notification gateway — Telegram alerts for all scripts and services |
| [duplicati](./duplicati/) | Encrypted backups — Vaultwarden → VPS (SFTP) + Google Drive |
| [frigate](./frigate/) | NVR with real-time object detection — 9 cameras, Coral TPU, macvlan IP 192.168.10.6 |
| [dockge](./dockge/) | Docker Compose stack management UI (replaced Portainer) |

### Productivity

| Stack | Description |
|-------|-------------|
| [vikunja](./vikunja/) | Self-hosted task manager (Todoist alternative) |
| [joplin](./joplin/) | Note-taking sync server (Evernote alternative) |
| [mealie](./mealie/) | Recipe manager & meal planner |
| [homepage](./homepage/) | Customisable service dashboard |

### Automation

| Stack | Description |
|-------|-------------|
| [lidarr-discovery](./lidarr-discovery/) | Discovers new artists via ListenBrainz Labs similar-artist API and adds them to Lidarr with `monitor=future`; runs as a one-shot container on a schedule |

### Other

| Stack | Description |
|-------|-------------|
| [fairybrains](./fairybrains/) | Personal website (Node.js), exposed via Cloudflare Tunnel |

## Scripts

Host-side scripts in [`scripts/`](./scripts/) — run via Unraid User Scripts (cron):

| Script | Schedule | Description |
|--------|----------|-------------|
| `check-services.sh` | every 5 min | HTTP health check for 20 services, alerts via apprise-api `critical` tag |
| `backup-photos-glacier.sh` | 2nd of month, 02:00 | Cold backup of 1.88 TB photo archive to AWS S3 Glacier Deep Archive via rclone crypt |
| `duplicati_notify.sh` | after-backup hook | Sends Duplicati result to apprise-api `backup` tag on Warning/Error |
| `weekly_summary.sh` | weekly | 7-day Duplicati summary report |
| `disk_usage_notify.sh` | daily | Disk usage check for `/mnt/user`, `/mnt/cache`, `/boot`; alerts if >85% |
| `watchtower-check.sh` | Sunday 10:00 | Checks for container image updates (monitor-only, Telegram via Watchtower) |
| `sync-vaultwarden.sh` | scheduled | SQLite-safe sync of Vaultwarden data to VPS backup instance |
| `setup-symlinks.sh` | array start | Restores `/usr/local/bin` symlinks after reboot |

### Notification tags (apprise-api)

| Tag | Used for |
|-----|----------|
| `critical` | Service down alerts |
| `backup` | Glacier, Duplicati results |
| `home` | Disk space, system events |

## Backups

| What | How | Where |
|------|-----|-------|
| Vaultwarden | Duplicati (scheduled) | VPS SFTP + Google Drive |
| Photo archive (1.88 TB) | `backup-photos-glacier.sh` + rclone crypt | AWS S3 Glacier Deep Archive (`eu-central-1`) |
| Homelab configs | `git push` | github.com/ilvits/homelab (public) |
| iCloud photos | icloudpd-watchdog | `/mnt/user/photoLibraries/` |
| Pi-hole config | rsync cron | `/mnt/user/backups/pihole/` |
| VPS stacks | rsync script on VPS | `/mnt/user/backups/vps/` |

## Networking

- **Reverse proxy**: Nginx Proxy Manager with SSL (Let's Encrypt)
- **External access**: Cloudflare Tunnel only — no ports exposed to the internet
- **VPN**: WireGuard + AmneziaWG on VPS, managed via WGDashboard (`wg.fairybrains.com`)
- **macvlan (br0)**: NPM (10.3), Seafile (10.7), Frigate (10.6) — dedicated LAN IPs
- **DNS**: Pi-hole on RPI4B (192.168.10.4, primary) + RPI3 (192.168.10.5, backup), synced via nebula-sync

## Usage

```bash
# Start a stack
cd /mnt/user/appdata/compose/<stack-name>
docker compose up -d

# Stop a stack
docker compose down

# View logs
docker compose logs -f

# Update all images in a stack
docker compose pull && docker compose up -d

# Restart a single container
docker compose restart <container-name>
```

## Security

- All secrets in `.env` files, excluded from git via `.gitignore`; `.env.example` committed with placeholders
- External access via Cloudflare Tunnel only — no inbound ports on home IP
- SSO via Authentik for supported services
- Encrypted backups via Duplicati; cold archive encrypted with rclone crypt (keys in Vaultwarden)
- IAM policy for Glacier has no `s3:DeleteObject` — intentional write-only protection
- WireGuard + AmneziaWG (obfuscated) for remote LAN access from restricted networks

## Notes

- `TZ` is intentionally omitted from Authentik server/worker — setting it breaks OAuth/SAML token validation
- Seafile uses `COMPOSE_FILE` env var (`seafile-server.yml`) — Dockge shows no compose file without it
- Vikunja requires `config.yml` with `service.publicurl` — env vars alone are not sufficient
- `media-stack`: all *arr apps + Lidarr route through Gluetun (WireGuard VPN gateway); ports published on Gluetun service
- Glacier backup runs on the 2nd of the month (1st is reserved for Unraid Parity Check)
- `lidarr-discovery` runs as a one-shot container triggered via Unraid User Scripts; uses ListenBrainz Labs `POST /similar-artists/json` endpoint
- `icloudpd-watchdog` handles 2FA interactively via Telegram — session cookie stored in `/mnt/user/appdata/icloudpd-{ilvits,kate}/`
