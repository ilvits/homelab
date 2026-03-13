#!/bin/bash
# setup-symlinks.sh — восстановление симлинков после перезагрузки
# Запускается автоматически через Unraid User Scripts при старте

SCRIPTS_DIR="/mnt/user/appdata/compose/scripts"

ln -sf "$SCRIPTS_DIR/check-services.sh" /usr/local/bin/check-services.sh
ln -sf "$SCRIPTS_DIR/watchtower-check.sh" /usr/local/bin/watchtower-check.sh

echo "$(date '+%Y-%m-%d %H:%M:%S') Symlinks restored" >> /var/log/setup-symlinks.log
