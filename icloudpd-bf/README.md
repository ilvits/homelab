# icloudpd-bf — ilvits iCloud Photos sync

Self-hosted iCloud Photos downloader for **ilvits** account, based on the
[boredazfcuk/docker-icloudpd](https://github.com/boredazfcuk/docker-icloudpd)
fork.

A sibling stack `icloudpd-bf-kate` runs the same setup for Kate's account.
Each Apple ID lives in its own container with its own cookies — they never
share state.

---

## Layout

```
icloudpd-bf/
  docker-compose.yml
  .env              <- create from .env.example, do not commit
  .env.example
  .gitignore
  README.md
```

Volumes:

| Host                                       | Container             | Purpose                            |
|--------------------------------------------|-----------------------|------------------------------------|
| `/mnt/user/appdata/icloudpd-bf`            | `/config`             | Cookies, keyring, container config |
| `/mnt/user/photoLibraries/ilvits/icloud`   | `/home/user/iCloud`   | Photo destination                  |

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

These are documented here so the compose file stays minimal.

### `skip_check: "true"` + `command_line_options: "--until-found 100"`

boredazfcuk runs a pre-check phase (`icloudpd --only-print-filenames`) on
every sync to enumerate the entire iCloud library before downloading
anything. On the ilvits account this enumeration hangs deterministically
on the 191st asset (likely a deleted-but-referenced asset or a Live Photo
edge case in pyicloud_ipd's HTTP handling — pyicloud has no socket timeout
and waits forever).

`skip_check=true` disables the pre-check. `--until-found 100` then tells
icloudpd to stop the download phase after 100 consecutive
already-downloaded files (counting from newest). Together they give us
incremental sync that never walks the whole library.

### `file_match_policy: name-size-dedup-with-suffix`

Compares files by `name + byte size`. Required for safe re-runs against
an existing on-disk library that came partly from upstream icloudpd and
partly from manual rsync.

### `folder_structure: "{:%Y/%m/%d}"`

Matches the layout already on disk
(`/mnt/user/photoLibraries/ilvits/icloud/YYYY/MM/DD/`). Changing this
would break dedup, since matches are scoped to the computed path.

### `user: ilvits` and `telegram_polling: "true"`

Together they enable the Telegram remote-trigger. Send the single word
`ilvits` to the bot in the chat → bot triggers an immediate sync within
60 seconds (polling interval).

When the MFA cookie is about to expire (within `notification_days: 7`),
the bot proactively sends a Telegram message; reply with the 6-digit
2FA code to refresh the cookie without `docker exec`.

### `silent_file_notifications: "true"`

Suppresses per-file Telegram notifications. Only auth events, cookie
expiry warnings, and errors get sent.

### `TZ: Europe/Minsk` and `user_id: 99 / group_id: 100`

Local timezone for log timestamps. UID 99 / GID 100 is the `nobody:users`
pair on Unraid — matches ownership of the photo library.

---

## Initialisation (one-time, interactive)

1. Create `.env` from the template:

   ```bash
   cd /mnt/user/appdata/compose/icloudpd-bf
   cp .env.example .env
   nano .env
   ```

   Required: `APPLE_ID`. Optional: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
   (leave `NOTIFICATION_TYPE=none` for the first run, switch to
   `Telegram` after init succeeds).

2. Bring the container up:

   ```bash
   docker compose up -d
   sleep 15
   docker logs icloudpd-bf 2>&1 | tail -20
   ```

3. Run the interactive initialisation. Enter the regular Apple ID
   password (NOT app-specific — those do not work with iCloud Photos):

   ```bash
   docker exec -it icloudpd-bf sync-icloud.sh --Initialise
   ```

   Expected prompt:

   ```
   a: * (***) ***-**-42
   Please enter two-factor authentication code or device index (a) to send SMS with a code:
   ```

   Wait for push on a trusted device, or type `a` (or other letter) to
   request SMS. Enter the 6-digit code. Cookie is stored in `/config/`.

4. Sync runs every `synchronisation_interval` seconds (default 2h).

---

## Re-authentication when cookie expires

MFA cookie lasts 60–90 days. When `notification_days` is reached, the bot
sends a Telegram message and waits for a 6-digit code reply in the same
chat. If you missed the notification or are not using Telegram:

```bash
docker exec -it icloudpd-bf sync-icloud.sh --Initialise
```

The same interactive flow as first init.

---

## Common operations

```bash
# Logs
docker logs -f icloudpd-bf

# Force a sync now (or send "ilvits" to the Telegram bot)
docker exec icloudpd-bf sync-icloud.sh

# Cookie expiry check
docker exec icloudpd-bf cat /config/expiry-info.txt 2>/dev/null

# Stop / start
cd /mnt/user/appdata/compose/icloudpd-bf
docker compose stop
docker compose start
```

---

## Files location

- Compose: `/mnt/user/appdata/compose/icloudpd-bf/`
- Cookies: `/mnt/user/appdata/icloudpd-bf/`
- Photos:  `/mnt/user/photoLibraries/ilvits/icloud/`
