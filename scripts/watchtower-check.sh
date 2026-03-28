#!/bin/bash
# watchtower-check.sh — проверка обновлений контейнеров
# Запускается еженедельно через cron
# Автор: ilvits | github.com/ilvits/homelab

# Загружаем переменные из .env
source /mnt/user/appdata/compose/scripts/.env

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --run-once \
  --monitor-only \
  --notification-url "$TELEGRAM_URL"
