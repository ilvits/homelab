#!/bin/bash
# duplicati_notify.sh — Duplicati backup result notifications
# Called by Duplicati as an after-backup script
# Notifications: apprise-api -> backup (Warning/Error only)

APPRISE_URL="http://localhost:8001/notify/backup"
LOG_FILE="/source/scripts/duplicati_notify.log"

notify() {
  local title="$1"
  local body="$2"
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body" \
    > /dev/null 2>&1
}

# === Duplicati environment variables ===
STATUS=$DUPLICATI__PARSED_RESULT
TASK=$DUPLICATI__BACKUP_NAME
SIZE_B=$DUPLICATI__LAST_BACKUP_SIZE
DURATION=$DUPLICATI__DURATION
DATE=$(date '+%Y-%m-%d %H:%M')

SIZE=$(awk -v b="$SIZE_B" 'BEGIN { printf "%.2f", b / 1048576 }')

# === Notify only on Warning/Error ===
if [[ "$STATUS" != "Success" ]]; then
  case "$STATUS" in
    Warning) ICON="WARNING" ;;
    Error)   ICON="ERROR" ;;
    *)       ICON="UNKNOWN" ;;
  esac

  BODY="$(printf 'Task: %s\nSize: %s MB\nDuration: %s\nStatus: %s' \
    "$TASK" "$SIZE" "$DURATION" "$STATUS")"

  notify "$ICON Duplicati: $TASK" "$BODY"
fi

# === Log everything (including successes) ===
echo "$DATE $TASK -> $STATUS (${SIZE} MB, ${DURATION})" >> "$LOG_FILE"

# === Rotate logs older than 30 days ===
tmpfile=$(mktemp)
awk -v today="$(date +%s)" '
  {
    split($1, d, "[-]")
    logtime = mktime(d[1]" "d[2]" "d[3]" 00 00 00")
    if (today - logtime < 2592000) print $0
  }
' "$LOG_FILE" > "$tmpfile" && mv "$tmpfile" "$LOG_FILE"
