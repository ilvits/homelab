#!/bin/bash
# disk_usage_notify.sh — disk space check with Telegram alerts
# Notifications: apprise-api -> home

APPRISE_URL="http://localhost:8001/notify/home"
THRESHOLD=85
MOUNTS=(
  "/mnt/user"
  "/mnt/cache"
  "/boot"
)

notify() {
  local title="$1"
  local body="$2"
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body" \
    > /dev/null 2>&1
}

MESSAGE_BODY=""
ALERT=0

for MOUNT in "${MOUNTS[@]}"; do
  if [[ -d "$MOUNT" ]]; then
    LINE=$(df -h "$MOUNT" | awk 'NR==2 {printf "* %s: %s free (%s used)", $6, $(NF-2), $(NF-1)}')
    USAGE=$(df "$MOUNT" | awk 'NR==2 {print $(NF-1)}' | tr -d '%')

    if [[ "$USAGE" -ge "$THRESHOLD" ]]; then
      ALERT=1
      LINE+=" WARNING"
    fi

    MESSAGE_BODY+="$LINE"$'\n'
  fi
done

if [[ "$ALERT" -eq 1 ]]; then
  notify "Disk Space Low" "$(printf 'Disk check:\n\n%s' "$MESSAGE_BODY")"
else
  notify "Disk Space OK" "$(printf 'Disk check:\n\n%s' "$MESSAGE_BODY")"
fi
