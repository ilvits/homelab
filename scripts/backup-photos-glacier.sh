#!/bin/bash
set +H

# Load secrets from .env (requires GLACIER_HEARTBEAT_TOKEN)
source /mnt/user/appdata/compose/scripts/.env

LOG="/var/log/glacier-backup.log"
TMP="/mnt/user/appdata/archive-ledger/tmp"
LEDGER="/mnt/user/appdata/archive-ledger/ledger.csv"
LEDGER_REPO="/root/homelab-private"
APPRISE_URL="http://localhost:8001/notify/backup"
CUTOFF_DAYS=30
ERRORS_FILE="/tmp/glacier-errors"
LOCK_FILE="/tmp/glacier-backup.lock"

log()    { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"; }
notify() {
  local title="$1"
  local body="$2"
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body" \
    > /dev/null 2>&1
}

# --- Lock: prevent concurrent runs ---
if [ -f "$LOCK_FILE" ]; then
  existing_pid=$(cat "$LOCK_FILE")
  if kill -0 "$existing_pid" 2>/dev/null; then
    log "SKIP: already running (PID $existing_pid)"
    notify "Glacier Backup" "WARNING: previous run still active (PID $existing_pid)"
    exit 0
  else
    log "WARN: removing stale lock (PID $existing_pid)"
    rm -f "$LOCK_FILE"
  fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE" "$ERRORS_FILE"' EXIT

mkdir -p "$TMP" "$(dirname "$LEDGER")"
echo 0 > "$ERRORS_FILE"

inc_errors() { echo $(($(cat "$ERRORS_FILE") + 1)) > "$ERRORS_FILE"; }
get_errors()  { cat "$ERRORS_FILE"; }

# pack_and_upload <src_path> <archive_name> <s3_subdir>
pack_and_upload() {
  local src="$1"
  local name="$2"
  local s3path="$3"
  local archive="$TMP/${name}.tar"

  log "Packing: $src -> $name"
  tar -cf "$archive" -C "$(dirname "$src")" "$(basename "$src")"
  local tar_rc=$?

  if [ $tar_rc -ne 0 ]; then
    log "ERROR tar: $name (exit $tar_rc)"
    rm -f "$archive"
    inc_errors
    return 1
  fi

  if [ ! -s "$archive" ]; then
    log "SKIP: $name — empty archive"
    rm -f "$archive"
    return 0
  fi

  local size sha
  size=$(du -sh "$archive" | cut -f1)
  sha=$(sha256sum "$archive" | awk '{print $1}')
  log "Archive ready: $name ($size)"

  rclone copy "$archive" "photos-crypt:${s3path}/" \
    --s3-storage-class DEEP_ARCHIVE \
    --transfers 4 \
    --bwlimit 2M \
    --log-file "$LOG" \
    --log-level INFO

  if [ $? -eq 0 ]; then
    echo "$(date '+%Y-%m-%d'),$name,$sha,OK" >> "$LEDGER"
    log "OK: $name (sha256: ${sha:0:16}...)"
    rm -f "$archive"
  else
    log "ERROR rclone: $name"
    rm -f "$archive"
    inc_errors
    return 1
  fi
}

push_ledger() {
  cp "$LEDGER" "$LEDGER_REPO/glacier/ledger.csv"
  cd "$LEDGER_REPO" && \
    git add glacier/ledger.csv && \
    git commit -m "glacier: update ledger $(date +%Y-%m-%d)" && \
    git push || log "WARN: git push failed, ledger safe locally"
  cd - > /dev/null
}

already_done() {
  grep -q ",$1," "$LEDGER" 2>/dev/null
}

log "=== Backup cycle started (PID $$) ==="
log "TMP: $TMP ($(df -h "$TMP" | tail -1 | awk '{print $4}') free)"

# --- 1. ilvits/icloud — YYYY/MM/ layout ---
while read -r monthdir; do
  year=$(basename "$(dirname "$monthdir")")
  month=$(basename "$monthdir")
  name="ilvits_icloud_${year}_${month}"
  already_done "$name" && continue
  age=$(find "$monthdir" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
  now=$(date +%s)
  [ -z "$age" ] && continue
  [ $(( (now - age) / 86400 )) -lt $CUTOFF_DAYS ] && continue
  pack_and_upload "$monthdir" "$name" "ilvits"
done < <(find "/mnt/user/photoLibraries/ilvits/icloud" -mindepth 2 -maxdepth 2 -type d | sort)

# --- 2. kate/icloud — YYYY/MM/DD/ layout ---
while read -r yeardir; do
  year=$(basename "$yeardir")
  while read -r monthdir; do
    month=$(basename "$monthdir")
    name="kate_icloud_${year}_${month}"
    already_done "$name" && continue
    age=$(find "$monthdir" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
    now=$(date +%s)
    [ -z "$age" ] && continue
    [ $(( (now - age) / 86400 )) -lt $CUTOFF_DAYS ] && continue
    pack_and_upload "$monthdir" "$name" "kate"
  done < <(find "$yeardir" -mindepth 1 -maxdepth 1 -type d | sort)
done < <(find "/mnt/user/photoLibraries/kate/icloud" -mindepth 1 -maxdepth 1 -type d | sort)

# --- 3. ilvits/photos/from_icloud — tar by year ---
while read -r yeardir; do
  year=$(basename "$yeardir")
  name="ilvits_from_icloud_${year}"
  already_done "$name" && continue
  age=$(find "$yeardir" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
  now=$(date +%s)
  [ -z "$age" ] && continue
  [ $(( (now - age) / 86400 )) -lt $CUTOFF_DAYS ] && continue
  pack_and_upload "$yeardir" "$name" "ilvits"
done < <(find "/mnt/user/photoLibraries/ilvits/photos/from_icloud" -mindepth 1 -maxdepth 1 -type d | sort)

# --- 4. ilvits/photos/!phone — tar by year ---
while read -r yeardir; do
  year=$(basename "$yeardir")
  name="ilvits_phone_${year}"
  already_done "$name" && continue
  pack_and_upload "$yeardir" "$name" "ilvits"
done < <(find "/mnt/user/photoLibraries/ilvits/photos/!phone" -mindepth 1 -maxdepth 1 -type d | sort)

# --- 5. ilvits/photos/!PICTURES + other — combined legacy archive ---
name="ilvits_legacy_001"
if ! already_done "$name"; then
  archive="$TMP/${name}.tar"
  log "Packing legacy: !PICTURES + other"
  tar -cf "$archive" \
    -C "/mnt/user/photoLibraries/ilvits/photos" \
    "!PICTURES" "other"
  if [ $? -eq 0 ] && [ -s "$archive" ]; then
    sha=$(sha256sum "$archive" | awk '{print $1}')
    rclone copy "$archive" "photos-crypt:ilvits/" \
      --s3-storage-class DEEP_ARCHIVE \
      --transfers 4 \
      --bwlimit 2M \
      --log-file "$LOG" \
      --log-level INFO
    if [ $? -eq 0 ]; then
      echo "$(date '+%Y-%m-%d'),$name,$sha,OK" >> "$LEDGER"
      log "OK: $name (sha256: ${sha:0:16}...)"
    else
      log "ERROR rclone: $name"; inc_errors
    fi
    rm -f "$archive"
  else
    log "ERROR tar: $name"; inc_errors; rm -f "$archive"
  fi
fi

# --- 6. kate/iPhone_mov ---
name="kate_iphone_mov"
if ! already_done "$name"; then
  pack_and_upload "/mnt/user/photoLibraries/kate/iPhone_mov" "$name" "kate"
fi

push_ledger

TOTAL_ERRORS=$(get_errors)

if [ "$TOTAL_ERRORS" -eq 0 ]; then
  curl -sf "http://localhost:3001/api/push/${GLACIER_HEARTBEAT_TOKEN}" > /dev/null 2>&1
  notify "Glacier Backup" "Backup completed successfully"
  log "=== Completed without errors ==="
else
  notify "Glacier Backup" "ERROR: $TOTAL_ERRORS failure(s) — check log"
  log "=== Completed with errors: $TOTAL_ERRORS ==="
  exit 1
fi
