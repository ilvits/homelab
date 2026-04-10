# iCloudPD Watchdog Bot

Telegram bot for automated iCloud photo sync via [icloudpd](https://github.com/icloudpd/icloudpd).

**Features:**
- Syncs multiple iCloud accounts sequentially
- Automatically detects expired sessions
- Interactive 2FA authorization directly through Telegram
- Notifications for newly downloaded files

---

## File structure

Place everything in `/mnt/user/appdata/compose/icloudpd-watchdog/`:

```
icloudpd-watchdog/
├── bot.py
├── Dockerfile
├── requirements.txt
├── docker-compose.yml
├── .env              <- create from .env.example (do not commit!)
├── .env.example
└── .gitignore
```

---

## Quick start

### 1. Get a Telegram token

Message [@BotFather](https://t.me/BotFather) -> `/newbot` -> copy the token.

### 2. Find your Chat ID

Message [@userinfobot](https://t.me/userinfobot) — it will reply with your `id`.

### 3. Create `.env`

```bash
cp .env.example .env
nano .env   # fill in all values
```

### 4. Start

```bash
cd /mnt/user/appdata/compose/icloudpd-watchdog
docker compose up -d --build
```

### 5. Check logs

```bash
docker logs -f icloudpd-watchdog
```

---

## First run and 2FA

On first run (or after a session expires) the bot automatically:

1. Detects an auth error during sync
2. Launches the `--auth-only` process
3. Messages you in Telegram asking for a verification code
4. You reply with 6 digits directly in the chat
5. The code is sent to the process and the session is saved to `/config/<name>/`
6. Sync resumes automatically

---

## Bot commands

| Command | Description |
|---|---|
| `/status` | Current status and account list |
| `/reauth ilvits` | Force re-authorization for an account |
| `/reauth kate` | Force re-authorization for an account |
| `/sync` | Run sync for all accounts now |
| `/help` | List commands |

---

## Volumes (docker-compose.yml)

| Host | Container | Purpose |
|---|---|---|
| `/mnt/user/appdata/icloudpd-ilvits` | `/config/ilvits` | Cookie/session for ilvits |
| `/mnt/user/appdata/icloudpd-kate` | `/config/kate` | Cookie/session for kate |
| `/mnt/user/photoLibraries/ilvits/icloud` | `/data/ilvits` | Photos for ilvits |
| `/mnt/user/photoLibraries/kate/icloud` | `/data/kate` | Photos for kate |

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | Yes | Token from @BotFather |
| `CHAT_ID` | Yes | Your Telegram chat_id |
| `ILVITS_USERNAME` | Yes | Apple ID (email) for first account |
| `ILVITS_PASSWORD` | Yes | Password for first account |
| `KATE_USERNAME` | Yes | Apple ID (email) for second account |
| `KATE_PASSWORD` | Yes | Password for second account |
| `ILVITS_FOLDER_STRUCTURE` | No | Folder pattern (default: `{:%Y/%m}`) |
| `KATE_FOLDER_STRUCTURE` | No | Folder pattern (default: `{:%Y/%m}`) |
| `SYNC_INTERVAL` | No | Sync interval in seconds (default: `3600`) |

---

## Notes

**App-specific password** — if two-factor authentication is enabled on your Apple ID (and it should be), Apple may require an app-specific password instead of the main one. Create one at [appleid.apple.com](https://appleid.apple.com) -> Security -> App-specific passwords.

**Session lifetime** — Apple invalidates cookies approximately every 30–90 days, sometimes sooner after an IP change. This is normal — the bot handles it automatically.

**Advanced Data Protection** — if iCloud Advanced Data Protection is enabled, some data types cannot be downloaded by icloudpd (Apple limitation).
