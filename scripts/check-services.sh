#!/bin/bash
# check-services.sh - homelab service availability check
# github.com/ilvits/homelab
#
# Checks the HTTP status code, not just whether curl managed to connect.
# The previous version ran "curl -s http://localhost:$port" and looked at the
# curl exit code alone, so any answer counted as healthy - including Joplin's
# 400 "Not allowed: HEAD" returned by a container whose app process was dead.

LOGFILE="/var/log/check-services.log"
APPRISE_URL="http://localhost:8001/notify/critical"
TIMEOUT=5

# Format: "name|port|path|expected_codes|host_header"
#   expected_codes - comma separated, matched after redirects are followed
#   host_header    - optional; needed when the service validates the origin
#
# Measured 2026-09-05: every service answers 200 once redirects are followed.
# Joplin is the exception - it compares the Host header against APP_BASE_URL
# and answers 404 "Invalid origin" to anything else, so it needs both an
# explicit path and the public hostname.
SERVICES=(
  "jellyfin|8096|/|200|"
  "sonarr|8989|/|200|"
  "radarr|7878|/|200|"
  "lidarr|8686|/|200|"
  "prowlarr|9696|/|200|"
  "jellyseerr|5055|/|200|"
  "bazarr|6767|/|200|"
  "qbittorrent|8080|/|200|"
  "authentik|9000|/|200|"
  "beszel|8090|/|200|"
  "homepage|3000|/|200|"
  "navidrome|4533|/|200|"
  "vaultwarden|4743|/|200|"
  "vikunja|3456|/|200|"
  "joplin|22300|/login|200|joplin.panteleyki.com"
  "filebrowser|8081|/|200|"
  "apprise-api|8001|/|200|"
  "sftpgo|2221|/|200|"
  "fairybrains|3005|/|200|"
  "duplicati|8200|/|200|"
)

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

FAIL_COUNT=0
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

notify() {
  local title=$1
  local body=$2
  [ "$DRY_RUN" -eq 1 ] && return 0
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body" \
    > /dev/null 2>&1
}

log() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "$*"
  else
    echo "$*" >> "$LOGFILE"
  fi
}

check_service() {
  local name=$1 port=$2 path=$3 expected=$4 host=$5
  local code

  if [ -n "$host" ]; then
    code=$(curl -s -L -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" \
      -H "Host: $host" "http://localhost:$port$path")
  else
    code=$(curl -s -L -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" \
      "http://localhost:$port$path")
  fi

  # A leading and trailing comma make the match exact, so "20" never matches
  # "200" and "40" never matches "404".
  if [ "$code" != "000" ] && [[ ",$expected," == *",$code,"* ]]; then
    log "$TIMESTAMP  OK    $name (:$port$path) $code"
    return 0
  fi

  FAIL_COUNT=$((FAIL_COUNT + 1))
  if [ "$code" = "000" ]; then
    log "$TIMESTAMP  FAIL  $name (:$port$path) no response"
    notify "Homelab: $name is DOWN" \
      "No HTTP response from $name on port $port after ${TIMEOUT}s"
  else
    log "$TIMESTAMP  FAIL  $name (:$port$path) $code, expected $expected"
    notify "Homelab: $name is DOWN" \
      "$name on port $port answered HTTP $code, expected $expected"
  fi
}

log "--- $TIMESTAMP ---"

for service in "${SERVICES[@]}"; do
  IFS='|' read -r name port path expected host <<< "$service"
  check_service "$name" "$port" "$path" "$expected" "$host"
done

if [ "$FAIL_COUNT" -eq 0 ]; then
  log "$TIMESTAMP  ALL OK (${#SERVICES[@]} services)"
else
  log "$TIMESTAMP  $FAIL_COUNT service(s) DOWN"
fi

log ""
