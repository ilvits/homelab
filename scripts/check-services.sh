#!/bin/bash
# check-services.sh — проверка доступности сервисов homelab
# Автор: ilvits | github.com/ilvits/homelab

LOGFILE="/var/log/check-services.log"
APPRISE_URL="http://localhost:8001/notify/critical"

# Формат: "название:порт"
SERVICES=(
  "jellyfin:8096"
  "sonarr:8989"
  "radarr:7878"
  "lidarr:8686"
  "prowlarr:9696"
  "jellyseerr:5055"
  "bazarr:6767"
  "qbittorrent:8080"
  "authentik:9000"
  "beszel:8090"
  "homepage:3000"
  "navidrome:4533"
  "vaultwarden:4743"
  "vikunja:3456"
  "joplin:22300"
  "filebrowser:8081"
  "apprise-api:8001"
  "sftpgo:2221"
  "fairybrains:3005"
  "duplicati:8200"
)

FAIL_COUNT=0
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

notify() {
  local title=$1
  local body=$2
  curl -sf -X POST "$APPRISE_URL" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"$title\", \"body\": \"$body\"}" \
    > /dev/null 2>&1
}

check_service() {
  local name=$1
  local port=$2
  if curl -s --max-time 5 "http://localhost:$port" > /dev/null 2>&1; then
    echo "$TIMESTAMP  OK    $name (:$port)" >> "$LOGFILE"
  else
    echo "$TIMESTAMP  FAIL  $name (:$port)" >> "$LOGFILE"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    notify "🔴 Homelab: $name is DOWN" "Service $name (port $port) is not responding"
  fi
}

echo "--- $TIMESTAMP ---" >> "$LOGFILE"

for service in "${SERVICES[@]}"; do
  name="${service%%:*}"
  port="${service##*:}"
  check_service "$name" "$port"
done

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo "$TIMESTAMP  ALL OK (${#SERVICES[@]} services)" >> "$LOGFILE"
else
  echo "$TIMESTAMP  $FAIL_COUNT service(s) DOWN" >> "$LOGFILE"
fi

echo "" >> "$LOGFILE"