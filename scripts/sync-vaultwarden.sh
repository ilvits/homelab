#!/bin/bash
# sync-vaultwarden.sh — sync Vaultwarden data from Unraid to VPS backup instance
# Runs on a cron schedule; performs a safe SQLite backup while the container is live

source /mnt/user/appdata/compose/scripts/.env

SRC="/mnt/user/appdata/vaultwarden"
TMP="/tmp/vw-sync"
LOG="/var/log/sync-vaultwarden.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

log "--- Sync started ---"

# Safe SQLite dump (works while the container is running)
mkdir -p "$TMP"
sqlite3 "$SRC/db.sqlite3" ".backup $TMP/db.sqlite3"
if [ $? -ne 0 ]; then
  log "ERROR: sqlite3 dump failed"
  rm -rf "$TMP"
  exit 1
fi

# Copy remaining data files
cp "$SRC/config.json" "$TMP/" 2>/dev/null
rsync -a "$SRC/attachments/" "$TMP/attachments/"
rsync -a "$SRC/sends/" "$TMP/sends/"

# rsa_key.pem is intentionally excluded — backup instance uses its own key

# Push to VPS
rsync -az --delete \
  --exclude='rsa_key.pem' \
  "$TMP/" \
  "${VPS_USER}@${VPS_HOST}:${VPS_VAULTWARDEN_DATA}/"

if [ $? -ne 0 ]; then
  log "ERROR: rsync to VPS failed"
  rm -rf "$TMP"
  exit 1
fi

# Restart backup container to pick up new database
ssh "${VPS_USER}@${VPS_HOST}" \
  "cd $(dirname "$VPS_VAULTWARDEN_DATA") && docker compose restart" >> "$LOG" 2>&1

rm -rf "$TMP"
log "Sync completed successfully"
