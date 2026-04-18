#!/bin/bash
# check-docker-vdisk.sh — Docker vDisk usage monitor
# Runs via Unraid User Scripts every 6 hours
# Alerts via apprise-api if usage exceeds threshold

APPRISE_URL="http://localhost:8001/notify/home"
THRESHOLD=10

USAGE=$(df /var/lib/docker | awk 'NR==2 {print $5}' | tr -d '%')
AVAIL=$(df -h /var/lib/docker | awk 'NR==2 {print $4}')
SIZE=$(df -h /var/lib/docker | awk 'NR==2 {print $2}')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
  curl -sf -X POST "$APPRISE_URL" \
    --data-urlencode "title=Docker vDisk Warning" \
    --data-urlencode "body=vDisk at ${USAGE}% (${AVAIL} of ${SIZE} free)
Run: docker image prune -f" \
    > /dev/null 2>&1
fi
