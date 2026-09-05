#!/bin/bash
# setup-symlinks.sh - restore symlinks after reboot
# Runs automatically via Unraid User Scripts on array start

SCRIPTS_DIR="/mnt/user/appdata/compose/scripts"

ln -sf "$SCRIPTS_DIR/check-services.sh" /usr/local/bin/check-services.sh
ln -sf "$SCRIPTS_DIR/watchtower-check.sh" /usr/local/bin/watchtower-check.sh
ln -sf /mnt/user/appdata/lazydocker/lazydocker /usr/local/bin/lazydocker

# docker compose CLI plugin. Previously delivered by the Compose.Manager
# plugin, which was removed. The binary is kept on the array, not on the USB
# boot drive: /boot is vfat mounted with fmask=0177, so the exec bit cannot be
# set there at all and chmod +x silently does nothing. Docker then refuses the
# plugin - "docker compose" reports only "unknown command", while the real
# reason ("permission denied") appears in the command list of "docker --help".
mkdir -p /usr/libexec/docker/cli-plugins
ln -sf /mnt/user/appdata/docker-cli-plugins/docker-compose \
       /usr/libexec/docker/cli-plugins/docker-compose

echo "$(date '+%Y-%m-%d %H:%M:%S') Symlinks restored" >> /var/log/setup-symlinks.log
