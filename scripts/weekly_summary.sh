#!/bin/bash
# weekly_summary.sh — weekly Duplicati backup report
# Notifications: apprise-api -> backup

APPRISE_URL="http://localhost:8001/notify/backup"
LOG_FILE="/mnt/user/appdata/compose/scripts/duplicati_notify.log"
DATE_NOW=$(date '+%Y-%m-%d %H:%M')
DATE_START=$(date -d '7 days ago' '+%Y-%m-%d')

notify() {
  local title="$1"
  local body="$2"
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body" \
    > /dev/null 2>&1
}

# === Analyse log for the last 7 days ===
WEEK_LOG=$(awk -v d="$DATE_START" '$0 >= d' "$LOG_FILE")

TOTAL=$(echo "$WEEK_LOG" | grep -c .)
OK=$(echo "$WEEK_LOG"    | grep -c "Success")
WARN=$(echo "$WEEK_LOG"  | grep -c "Warning")
ERR=$(echo "$WEEK_LOG"   | grep -c "Error")

FAILED_TASKS=$(echo "$WEEK_LOG" | grep -E "Warning|Error")

if [[ "$ERR" -eq 0 && "$WARN" -eq 0 ]]; then
  TITLE="Duplicati: clean week"
  BODY="$(printf 'Period: %s — %s\nTotal tasks: %d\nSuccessful: %d\nNo errors found.' \
    "$DATE_START" "$DATE_NOW" "$TOTAL" "$OK")"
else
  TITLE="Duplicati: weekly report"
  BODY="$(printf 'Period: %s — %s\nTotal: %d | OK: %d | Warnings: %d | Errors: %d\n\nFailed tasks:\n%s' \
    "$DATE_START" "$DATE_NOW" "$TOTAL" "$OK" "$WARN" "$ERR" "$FAILED_TASKS")"
fi

notify "$TITLE" "$BODY"
