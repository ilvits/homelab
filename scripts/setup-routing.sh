#!/bin/bash
# setup-routing.sh — fix CAM subnet routing after Docker/Frigate start
# Trigger: Array Started (with delay to allow containers to come up)
# Problem: Frigate macvlan creates vhost1/eth1 with 192.168.30.1 — kernel
#   prefers these linkdown interfaces over the correct gateway route,
#   making 192.168.30.0/24 unreachable from Unraid host.
# Fix: remove macvlan-created routes, add correct route via gateway.

LOG="/var/log/setup-routing.log"
GATEWAY="192.168.10.1"
CAM_NET="192.168.30.0/24"
IFACE="br0"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

log "Waiting 120s for Docker containers to start..."
sleep 120

log "Fixing CAM subnet routing..."

# Remove macvlan-created routes that conflict (linkdown — unusable)
for iface in vhost1 eth1; do
    if ip route show | grep -q "${CAM_NET} dev ${iface}"; then
        ip route del "${CAM_NET}" dev "${iface}" 2>/dev/null \
            && log "Removed route via ${iface}" \
            || log "WARN: failed to remove route via ${iface}"
    fi
done

# Add correct route via LAN gateway if not already present
if ip route get 192.168.30.101 2>/dev/null | grep -q "via ${GATEWAY}"; then
    log "Route already correct — no changes needed"
else
    ip route add "${CAM_NET}" via "${GATEWAY}" dev "${IFACE}" 2>/dev/null \
        && log "Route added: ${CAM_NET} via ${GATEWAY}" \
        || log "ERROR: failed to add route"
fi

# Verify
RESULT=$(ip route get 192.168.30.101 2>/dev/null)
log "Verify: ${RESULT}"
