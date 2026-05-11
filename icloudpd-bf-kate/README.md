# icloudpd-bf-kate — Kate's iCloud Photos sync

Self-hosted iCloud Photos downloader for **Kate's** account, based on the
[boredazfcuk/docker-icloudpd](https://github.com/boredazfcuk/docker-icloudpd)
fork.

A sibling stack `icloudpd-bf` runs the same setup for ilvits's account.
Each Apple ID lives in its own container with its own cookies — they never
share state.

---

## Layout

```
icloudpd-bf-kate/
  docker-compose.yml
  .env              <- create from .env.example, do not commit
  .env.example
  .gitignore
  README.md
```

Volumes:

| Host                                       | Container             | Purpose                            |
|--------------------------------------------|-----------------------|------------------------------------|
| `/mnt/user/appdata/icloudpd-bf-kate`       | `/config`             | Cookies, keyring, container config |
| `/mnt/user/photoLibraries/kate/icloud`     | `/home/user/iCloud`   | Photo destination                  |

---

## Why this fork and not upstream icloudpd

Upstream `icloud-photos-downloader/icloud_photos_downloader` (1.32.x) has a
2FA regression: on some Apple accounts push notifications stop being
delivered to trusted devices, while icloud.com web login still works
(GitHub issues #930, #925, #1243).

The boredazfcuk fork lets you pick between SMS and push during interactive
initialisation, which works around accounts where push silently fails.

The original automated stack `icloudpd-watchdog` (a custom Python Telegram
bot wrapper around upstream icloudpd) was retired in May 2026 in favour of
this one.

---

## Non-obvious config decisions

These mirror the decisions documented in `icloudpd-bf` (ilvits). Same
fork, same Apple API, same workarounds. See `icloudpd-bf/README.md` for
the longer rationale. Quick summary:

| Setting | Why |
|---|---|
| `skip_check: "true"` | Avoids pre-check phase that hangs on certain assets |
| `--until-found 100` | Incremental sync — stops after 100 consecutive existing files |
| `file_match_policy: name-size-dedup-with-suffix` | Safe re-runs against existing library |
| `folder_structure: "{:%Y/%m/%d}"` | Matches existing on-disk layout |
| `user: kate` + `telegram_polling: "true"` | Telegram trigger word for forced sync; reply with 2FA code on cookie expiry |
| `silent_file_notifications: "true"` | Only meaningful events sent to Telegram |
| `TZ: Europe/Minsk`, `user_id: 99 / group_id: 100` | Local time, `nobody:users` ownership |

---

## Initialisation (one-time, interactive)

> ⚠️ Make sure the `icloudpd-bf` container (ilvits) is in idle (not actively
> syncing) before starting Kate's init. Two parallel API hammerings from the
> same IP can trigger Apple's account-level throttling.

```bash
docker stats icloudpd-bf --no-stream
```

1. Create `.env` from the template:

   ```bash
   cd /mnt/user/appdata/compose/icloudpd-bf-kate
   cp .env.example .env
   nano .env
   ```

   Required: `APPLE_ID` (Kate's email). Optional: `TELEGRAM_TOKEN`,
   `TELEGRAM_CHAT_ID`. Note: if both stacks share the **same** Telegram
   bot token, polling will not work reliably (Telegram delivers each
   update to only one client). Either use a dedicated bot for Kate or
   keep one of the stacks on `NOTIFICATION_TYPE=none`.

2. Bring the container up:

   ```bash
   docker compose up -d
   sleep 15
   docker logs icloudpd-bf-kate 2>&1 | tail -20
   ```

3. Run the interactive initialisation (Kate's regular Apple ID password
   required at the prompt):

   ```bash
   docker exec -it icloudpd-bf-kate sync-icloud.sh --Initialise
   ```

   Wait for push on Kate's trusted device, or type the device letter (`a`,
   `b`, ...) to request SMS. Enter the 6-digit code.

4. Sync runs every `synchronisation_interval` seconds (default 2h).

---

## Re-authentication when cookie expires

MFA cookie lasts 60–90 days. When `notification_days` is reached, the bot
sends a Telegram message and waits for a 6-digit code reply in the same
chat. If not using Telegram:

```bash
docker exec -it icloudpd-bf-kate sync-icloud.sh --Initialise
```

---

## Common operations

```bash
# Logs
docker logs -f icloudpd-bf-kate

# Force a sync now (or send "kate" to the Telegram bot)
docker exec icloudpd-bf-kate sync-icloud.sh

# Stop / start
cd /mnt/user/appdata/compose/icloudpd-bf-kate
docker compose stop
docker compose start
```

---

## Files location

- Compose: `/mnt/user/appdata/compose/icloudpd-bf-kate/`
- Cookies: `/mnt/user/appdata/icloudpd-bf-kate/`
- Photos:  `/mnt/user/photoLibraries/kate/icloud/`
