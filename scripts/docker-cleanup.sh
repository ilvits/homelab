#!/bin/bash
# docker-cleanup.sh - safe reclaim of docker.img space on Unraid
#
# Deliberately avoids "docker image prune -a": stacks stopped via Dockge have
# no containers at all, so their images look unreferenced and would be removed.
# Instead, images declared in compose files are treated as protected.
#
# Usage: docker-cleanup.sh [--dry-run] [--volumes]

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/.env" ] && source "$SCRIPT_DIR/.env"

APPRISE="http://localhost:8001/notify/home"
COMPOSE_ROOT="/mnt/user/appdata/compose"
DOCKER_ROOT="/var/lib/docker"
LOG="/var/log/docker-cleanup.log"
CACHE_KEEP="168h"                     # keep build cache younger than 7 days
DRY_RUN=0
PRUNE_VOLUMES=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --volumes) PRUNE_VOLUMES=1 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

notify() {
  curl -s -X POST "$APPRISE" \
    --data-urlencode "title=Docker Cleanup" \
    --data-urlencode "body=$1" > /dev/null
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: $*"
  else
    "$@"
  fi
}

usage_pct() { df --output=pcent "$DOCKER_ROOT" | tail -1 | tr -dc '0-9'; }
usage_line() { df -h "$DOCKER_ROOT" | tail -1 | awk '{print $3" / "$2" ("$5")"}'; }

BEFORE_PCT=$(usage_pct)
log "=== Start (dry_run=$DRY_RUN) - docker.img: $(usage_line) ==="

# --- Build the protected image set from compose files -----------------------
declare -A PROTECT_REF=()
declare -A PROTECT_REPO=()

while read -r ref; do
  [ -z "$ref" ] && continue
  if [[ "$ref" == *'${'* ]]; then
    # unresolved variable in the tag: protect the whole repository
    PROTECT_REPO["${ref%%:*}"]=1
    continue
  fi
  [[ "$ref" != *:* ]] && ref="${ref}:latest"
  PROTECT_REF["$ref"]=1
  PROTECT_REPO["${ref%%:*}"]=1
done < <(
  find "$COMPOSE_ROOT" -maxdepth 2 -type f \( -name '*.yaml' -o -name '*.yml' \) \
    -exec grep -hE '^[[:space:]]*image:[[:space:]]*' {} + 2>/dev/null \
    | sed -E 's/^[[:space:]]*image:[[:space:]]*//; s/^["'\'']//; s/["'\'']?[[:space:]]*(#.*)?$//' \
    | sort -u
)
log "Protected images from compose files: ${#PROTECT_REF[@]} refs, ${#PROTECT_REPO[@]} repos"

# Explicit keep-list: substring match against the repository name.
# Needed for images built locally (no "image:" line in compose) or for
# images whose container is created ad-hoc and does not persist.
KEEP_PATTERNS=(
  "lidarr-discovery"
  "containrrr/watchtower"
)

# Images referenced by any container, running or not
declare -A IN_USE=()
while read -r img; do [ -n "$img" ] && IN_USE["$img"]=1; done < <(
  docker ps -aq | xargs -r docker inspect --format '{{.Image}}' 2>/dev/null
)


# --- 2. Build cache ---------------------------------------------------------
log "Pruning build cache older than $CACHE_KEEP"
run docker builder prune -f --filter "until=$CACHE_KEEP" >> "$LOG" 2>&1

# --- 3. Dangling images (always safe) ---------------------------------------
log "Pruning dangling images"
run docker image prune -f >> "$LOG" 2>&1

# --- 4. Unreferenced images, excluding protected ones -----------------------
REMOVED=0
while read -r id ref; do
  [ "$ref" = "<none>:<none>" ] && continue
  [ -n "${IN_USE[$id]:-}" ] && continue
  [ -n "${PROTECT_REF[$ref]:-}" ] && continue
  repo="${ref%%:*}"
  [ -n "${PROTECT_REPO[$repo]:-}" ] && { log "KEEP (repo in compose): $ref"; continue; }
  keep=0
  for pat in "${KEEP_PATTERNS[@]}"; do
    case "$repo" in *"$pat"*) log "KEEP (keep-list): $ref"; keep=1; break ;; esac
  done
  [ "$keep" -eq 1 ] && continue
  log "Removing unreferenced image: $ref"
  run docker rmi "$id" >> "$LOG" 2>&1 && REMOVED=$((REMOVED + 1))
done < <(docker images --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}}')
log "Images removed: $REMOVED"

# --- 5. Volumes: report only unless --volumes -------------------------------
ORPHANS=$(docker volume ls -qf dangling=true | wc -l)
if [ "$ORPHANS" -gt 0 ]; then
  if [ "$PRUNE_VOLUMES" -eq 1 ]; then
    log "Pruning $ORPHANS dangling volumes"
    run docker volume prune -f >> "$LOG" 2>&1
  else
    log "WARN: $ORPHANS dangling volumes found - review manually, then rerun with --volumes"
    docker volume ls -qf dangling=true | tee -a "$LOG"
  fi
fi

# --- 6. Stopped containers: report only -------------------------------------
STOPPED=$(docker ps -a --filter status=exited --filter status=created --format '{{.Names}}')
[ -n "$STOPPED" ] && log "NOTE: stopped containers present (not touched): $(echo "$STOPPED" | tr '\n' ' ')"

AFTER_PCT=$(usage_pct)
SUMMARY="docker.img: ${BEFORE_PCT}% -> ${AFTER_PCT}% | $(usage_line)
images removed: $REMOVED, dangling volumes: $ORPHANS"
log "=== Done === $SUMMARY"

if [ "$DRY_RUN" -eq 0 ]; then
  if [ "$AFTER_PCT" -ge 90 ]; then
    notify "WARNING: cleanup finished but disk is still at ${AFTER_PCT}%
$SUMMARY"
  else
    notify "$SUMMARY"
  fi
fi
