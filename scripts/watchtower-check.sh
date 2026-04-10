#!/bin/bash
# watchtower-check.sh — weekly container update check
# Runs via cron; reports available updates to Telegram via Watchtower monitor-only mode

# Load secrets from .env
source /mnt/user/appdata/compose/scripts/.env

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --run-once \
  --monitor-only \
  --notification-url "$TELEGRAM_URL"
