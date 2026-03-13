#!/bin/bash
# watchtower-check.sh — проверка обновлений контейнеров
# Запускается еженедельно через cron
# Автор: ilvits | github.com/ilvits/homelab

TELEGRAM_URL="telegram://8623807957:***REMOVED***@telegram?channels=-1003574659412:105"

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --run-once \
  --monitor-only \
  --notification-url "$TELEGRAM_URL"
