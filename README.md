# 🏠 Homelab

Personal homelab running on **Unraid** with 20 stacks, managed via Docker Compose.

## 🖥️ Hardware

| Component | Spec |
|-----------|------|
| **CPU** | Intel N100 |
| **RAM** | 32 GB |
| **Cache (appdata)** | SSD |
| **Array (media/data)** | HDD |
| **OS** | Unraid |
| **Additional** | Raspberry Pi 3 & 4 (DNS), MikroTik Router (WireGuard VPN) |

## 📁 Structure

All stacks live in `/mnt/user/appdata/compose/`, each in its own subdirectory:

```
compose/
├── authentik/
├── apprise-api/
├── beszel/
├── cloudflared/
├── duplicati/
├── fairybrains/
├── filebrowser/
├── frigate/
├── homepage/
├── icloudpd/
├── immich/
├── joplin/
├── media-stack/
├── navidrome/
├── npm/
├── seafile/
├── sftpgo/
├── vaultwarden/
├── vikunja/
└── scripts/
    ├── check-services.sh     # Service health check (cron every 5 min)
    ├── watchtower-check.sh   # Weekly update notifications (cron every Sunday 10:00)
    └── setup-symlinks.sh     # Restore symlinks after reboot (Unraid User Scripts)
```

Each stack has its own `docker-compose.yml` and `.env` file. Secrets are kept in `.env` files and excluded from version control via `.gitignore`.

## 🧩 Stacks

### 🔐 Auth & Access
| Stack | Description |
|-------|-------------|
| [authentik](./authentik/) | SSO / Identity Provider — centralised auth for all services |
| [npm](./npm/) | Nginx Proxy Manager — reverse proxy with SSL termination |
| [cloudflared](./cloudflared/) | Cloudflare Tunnel — secure external access without open ports |
| [vaultwarden](./vaultwarden/) | Self-hosted Bitwarden-compatible password manager |

### 📸 Media & Files
| Stack | Description |
|-------|-------------|
| [media-stack](./media-stack/) | Full *arr suite — Jellyfin, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Jellyseerr, qBittorrent, FlareSolverr |
| [immich](./immich/) | Photo & video backup (Google Photos alternative), with OpenVINO ML |
| [seafile](./seafile/) | File sync & share (Dropbox alternative) |
| [navidrome](./navidrome/) | Music streaming server (Spotify alternative) |
| [icloudpd](./icloudpd/) | Automated iCloud photo download to local storage |
| [filebrowser](./filebrowser/) | Web-based file manager |
| [sftpgo](./sftpgo/) | SFTP / WebDAV server for secure file transfers |

### 🔔 Notifications & Monitoring
| Stack | Description |
|-------|-------------|
| [beszel](./beszel/) | Lightweight server & container monitoring dashboard |
| [apprise-api](./apprise-api/) | Multi-platform notification gateway (Telegram, email, etc.) |
| [duplicati](./duplicati/) | Encrypted cloud & local backups |
| [frigate](./frigate/) | NVR with real-time object detection (Intel GPU passthrough) |

### 🗂️ Productivity
| Stack | Description |
|-------|-------------|
| [vikunja](./vikunja/) | Self-hosted task manager (Todoist alternative) |
| [joplin](./joplin/) | Note-taking app with sync server (Evernote alternative) |
| [homepage](./homepage/) | Customisable dashboard for all services |

### 🌐 Other
| Stack | Description |
|-------|-------------|
| [fairybrains](./fairybrains/) | Personal website (Node.js) |

## 🚀 Usage

### Start a stack
```bash
cs <stack-name>   # cd into stack directory
dc up -d          # start containers
```

### Stop a stack
```bash
dc down
```

### View logs
```bash
dc logs -f
```

### Update images
```bash
dc pull
dc up -d
```

### Restart a single container
```bash
dc restart <container-name>
```

## 🤖 Scripts

| Script | Description | Schedule |
|--------|-------------|----------|
| [check-services.sh](./scripts/check-services.sh) | Checks all 20 services via HTTP, sends Telegram alert on failure | Every 5 min (cron) |
| [watchtower-check.sh](./scripts/watchtower-check.sh) | Checks for new container images, notifies via Telegram | Every Sunday 10:00 (cron) |
| [setup-symlinks.sh](./scripts/setup-symlinks.sh) | Restores `/usr/local/bin` symlinks to scripts after reboot | At array start (Unraid User Scripts) |

Scripts are stored in `/mnt/user/appdata/compose/scripts/` and symlinked to `/usr/local/bin/`.
Secrets (Telegram token, etc.) are stored in `scripts/.env`, excluded from git.

## 🌐 Networking

- **Reverse proxy**: Nginx Proxy Manager with SSL (Let's Encrypt)
- **External access**: Cloudflare Tunnel (no open ports)
- **VPN**: WireGuard on MikroTik router
- **macvlan**: NPM, Seafile, Frigate run on dedicated IPs on the local network (`br0`)
- **DNS**: Pi-hole on Raspberry Pi 3 & 4

## 🔒 Security

- All secrets stored in `.env` files, excluded from git via `.gitignore`
- External access via Cloudflare Tunnel only — no ports exposed to the internet
- SSO via Authentik for supported services
- Encrypted backups via Duplicati (VPS + Google Drive)

## 📋 Notes

- `TZ=Europe/Moscow` is set in all stacks (except Authentik — intentionally omitted per [official docs](https://docs.goauthentik.io/))
- Authentik image: `ghcr.io/goauthentik/server:2026.2.1`
- Seafile uses `COMPOSE_FILE` env var for multi-file compose setup
- Vikunja requires `config.yml` with `service.publicurl` — env vars alone are not sufficient
