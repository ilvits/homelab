#!/bin/bash
# setup-symlinks.sh — restore symlinks after reboot
# Runs automatically via Unraid User Scripts on array start

SCRIPTS_DIR="/mnt/user/appdata/compose/scripts"

ln -sf "$SCRIPTS_DIR/check-services.sh" /usr/local/bin/check-services.sh
ln -sf "$SCRIPTS_DIR/watchtower-check.sh" /usr/local/bin/watchtower-check.sh
ln -sf /mnt/user/appdata/lazydocker/lazydocker /usr/local/bin/lazydocker

echo "$(date '+%Y-%m-%d %H:%M:%S') Symlinks restored" >> /var/log/setup-symlinks.log
