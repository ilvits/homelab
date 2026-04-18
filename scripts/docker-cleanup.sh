#!/bin/bash
# docker-cleanup.sh — weekly Docker dangling image and build cache cleanup
# Runs via Unraid User Scripts every Sunday at 03:00
# Reports freed space to Telegram via apprise-api

APPRISE_URL="http://localhost:8001/notify/home"
LOGFILE="/var/log/docker-cleanup.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

log() { echo "$TIMESTAMP  $1" | tee -a "$LOGFILE"; }

notify() {
  local title=$1
  local body=$2
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body" \
    > /dev/null 2>&1
}

get_vdisk_used() {
  df /var/lib/docker | awk 'NR==2 {print $3}'
}

log "=== Docker cleanup started ==="

BEFORE=$(get_vdisk_used)

# Remove dangling images (<none>:<none>) — left over after compose pull + up -d
PRUNED_IMAGES=$(docker image prune -f 2>&1)
IMAGES_RECLAIMED=$(echo "$PRUNED_IMAGES" | grep "Total reclaimed" | grep -oP '[\d.]+\s*\w+' | tail -1)
log "Images pruned: ${IMAGES_RECLAIMED:-0B}"

# Remove unused build cache (icloudpd-watchdog, lidarr-discovery builds)
PRUNED_CACHE=$(docker buildx prune -f 2>&1)
CACHE_RECLAIMED=$(echo "$PRUNED_CACHE" | grep "Total reclaimed" | grep -oP '[\d.]+\s*\w+' | tail -1)
log "Build cache pruned: ${CACHE_RECLAIMED:-0B}"

AFTER=$(get_vdisk_used)
FREED_KB=$(( BEFORE - AFTER ))
FREED_MB=$(( FREED_KB / 1024 ))

VDISK_USAGE=$(df /var/lib/docker | awk 'NR==2 {print $5}')
VDISK_AVAIL=$(df -h /var/lib/docker | awk 'NR==2 {print $4}')

log "vDisk: ${VDISK_USAGE} used, ${VDISK_AVAIL} free"
log "=== Cleanup complete, freed ~${FREED_MB}MB ==="

notify "Docker Cleanup" "Freed ~${FREED_MB}MB | vDisk: ${VDISK_USAGE} used, ${VDISK_AVAIL} free"
