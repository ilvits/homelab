# Docker daemon configuration

## Why

Docker's built-in default address pools are:

    { "base": "172.17.0.0/12", "size": 16 }   # 172.17 - 172.31, 15 blocks
    { "base": "192.168.0.0/16", "size": 20 }  # fallback, /20 blocks

With ~28 compose stacks the first pool was exhausted and allocation spilled
into 192.168.0.0/16. One stack (lidarr-discovery) received 192.168.16.0/20,
which spans 192.168.16.0 - 192.168.31.255 and therefore swallowed the camera
subnet 192.168.30.0/24. Traffic to the cameras was routed into a docker bridge
instead of the MikroTik gateway.

The next free block would have been 192.168.0.0/20, covering the LAN
192.168.10.0/24.

## Fix

    { "base": "172.16.0.0/12", "size": 24 }
    { "base": "10.100.0.0/16", "size": 24 }

Neither pool overlaps the LAN (192.168.10.0/24), the camera subnet
(192.168.30.0/24) or the VPN subnets (10.8.x).

Note: 172.16.0.0/12 is already fully occupied by pre-existing /16 networks,
so new networks are allocated from 10.100.0.0/16 (256 blocks).

## Persistence

/etc is a tmpfs on Unraid. The file lives on the flash drive and is copied
into place at boot by /boot/config/go:

    mkdir -p /etc/docker
    cp /boot/config/docker-custom/daemon.json /etc/docker/daemon.json

## Applying changes

Edit /boot/config/docker-custom/daemon.json, copy it to /etc/docker/, then
restart Docker from the web UI (Settings -> Docker -> Enable Docker: No ->
Apply -> Yes). The console rc.docker script does not start the daemon
reliably.

`dockerd --validate --config-file <path>` only checks syntax, not address
availability -- a syntactically valid pool can still fail with
"all predefined address pools have been fully subnetted".
