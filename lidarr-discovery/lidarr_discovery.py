#!/usr/bin/env python3
"""
Lidarr ListenBrainz Discovery
==============================
Discovers new artists via ListenBrainz Labs Similar Artists API and adds them to Lidarr.

Key insight — overlap scoring with a window:
  MIN_OVERLAP_SCORE filters out random one-off suggestions.
  MAX_OVERLAP_SCORE filters out mega-popular mainstream artists that appear
  as "similar" to everything due to their sheer size in community listening data.
  The sweet spot between the two is where genuine discoveries live.

Environment variables:
  LIDARR_URL              — e.g. http://192.168.10.10:8686  (required)
  LIDARR_API_KEY          — Lidarr Settings → General → API Key  (required)
  LIDARR_ROOT_FOLDER      — e.g. /mediafiles/music  (default: /music)
  LIDARR_QUALITY_PROFILE  — profile name, e.g. "Lossless"  (default: first)
  LIDARR_METADATA_PROFILE — profile name, e.g. "Standard"  (default: first)
  LIDARR_MONITOR_MODE     — none | future | all  (default: future)
                            none   = добавить без мониторинга, ничего не качать
                            future = мониторить только новые релизы (рекомендуется)
                            all    = качать всю дискографию сразу (осторожно!)
  DISCOVERY_DEPTH         — 1 or 2  (default: 1)
  MIN_OVERLAP_SCORE       — minimum overlap count  (default: 10)
  MAX_OVERLAP_SCORE       — maximum overlap count, 0 = no limit  (default: 80)
  BATCH_SIZE              — MBIDs per API request  (default: 50)
  MAX_ADD                 — max artists to add per run  (default: 10)
  CACHE_TTL_DAYS          — days before cached LB results expire  (default: 30)
  DRY_RUN                 — true/false  (default: false)
"""

import json
import logging
import os
import time

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LIDARR_URL = os.environ["LIDARR_URL"].rstrip("/")
LIDARR_API_KEY = os.environ["LIDARR_API_KEY"]
LIDARR_ROOT_FOLDER = os.environ.get("LIDARR_ROOT_FOLDER", "/music")
LIDARR_QUALITY_PROFILE = os.environ.get("LIDARR_QUALITY_PROFILE", "")
LIDARR_METADATA_PROFILE = os.environ.get("LIDARR_METADATA_PROFILE", "")

LIDARR_MONITOR_MODE = os.environ.get("LIDARR_MONITOR_MODE", "future").lower()
assert LIDARR_MONITOR_MODE in ("none", "future", "all"), \
    f"LIDARR_MONITOR_MODE must be none/future/all, got: {LIDARR_MONITOR_MODE}"

DISCOVERY_DEPTH = int(os.environ.get("DISCOVERY_DEPTH", "1"))
MIN_OVERLAP_SCORE = int(os.environ.get("MIN_OVERLAP_SCORE", "10"))
MAX_OVERLAP_SCORE = int(os.environ.get("MAX_OVERLAP_SCORE", "80"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "50"))
MAX_ADD = int(os.environ.get("MAX_ADD", "10"))
CACHE_TTL_DAYS = int(os.environ.get("CACHE_TTL_DAYS", "30"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

LB_LABS_URL = "https://labs.api.listenbrainz.org/similar-artists/json"
LB_ALGORITHM = "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"

CACHE_FILE = "/app/data/cache.json"
CACHE_TTL = CACHE_TTL_DAYS * 86400  # seconds


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {"lb_results": {}, "lb_timestamps": {}}


def save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    # Ensure timestamps key exists (for old cache files without it)
    cache.setdefault("lb_timestamps", {})
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def is_cache_valid(mbid: str, cache: dict) -> bool:
    """Return True if the cached entry exists and hasn't expired."""
    if mbid not in cache.get("lb_results", {}):
        return False
    ts = cache.get("lb_timestamps", {}).get(mbid, 0)
    return (time.time() - ts) < CACHE_TTL


def cache_put(mbid: str, data: list[dict], cache: dict) -> None:
    cache.setdefault("lb_results", {})[mbid] = data
    cache.setdefault("lb_timestamps", {})[mbid] = time.time()


def evict_expired(cache: dict) -> int:
    """Remove expired entries. Returns count of evicted entries."""
    now = time.time()
    timestamps = cache.get("lb_timestamps", {})
    expired = [
        mbid for mbid, ts in timestamps.items()
        if (now - ts) >= CACHE_TTL
    ]
    for mbid in expired:
        cache.get("lb_results", {}).pop(mbid, None)
        timestamps.pop(mbid, None)
    return len(expired)


# ---------------------------------------------------------------------------
# ListenBrainz Labs client
# ---------------------------------------------------------------------------
def lb_similar_batch(mbids: list[str]) -> dict[str, list[dict]]:
    try:
        payload = [{"artist_mbids": mbids, "algorithm": LB_ALGORITHM}]
        r = requests.post(LB_LABS_URL, json=payload, timeout=30)
        r.raise_for_status()
        results = r.json()
        grouped: dict[str, list[dict]] = {mbid: [] for mbid in mbids}
        for item in results:
            ref = item.get("reference_mbid", "")
            if ref in grouped:
                grouped[ref].append({
                    "mbid": item.get("artist_mbid", ""),
                    "name": item.get("name", ""),
                    "score": int(item.get("score", 0)),
                })
        return grouped
    except requests.RequestException as exc:
        log.warning("ListenBrainz Labs request failed: %s", exc)
        return {mbid: [] for mbid in mbids}


def lb_similar_all(mbids: list[str], cache: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    uncached: list[str] = []

    for mbid in mbids:
        if is_cache_valid(mbid, cache):
            result[mbid] = cache["lb_results"][mbid]
        else:
            uncached.append(mbid)

    if uncached:
        log.info("  Fetching %d MBIDs from ListenBrainz Labs in batches of %d...",
                 len(uncached), BATCH_SIZE)
        for i in range(0, len(uncached), BATCH_SIZE):
            batch = uncached[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(uncached) + BATCH_SIZE - 1) // BATCH_SIZE
            log.info("  Batch %d/%d (%d MBIDs)...", batch_num, total_batches, len(batch))
            batch_results = lb_similar_batch(batch)
            for mbid, similar in batch_results.items():
                result[mbid] = similar
                cache_put(mbid, similar, cache)
            time.sleep(0.5)
    else:
        log.info("  All results served from cache (TTL=%d days)", CACHE_TTL_DAYS)

    return result


# ---------------------------------------------------------------------------
# Lidarr client
# ---------------------------------------------------------------------------
class LidarrClient:
    def __init__(self, url: str, api_key: str) -> None:
        self.url = url
        self.headers = {"X-Api-Key": api_key}

    def _get(self, path: str, **params) -> list | dict:
        r = requests.get(f"{self.url}/api/v1{path}", headers=self.headers,
                         params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict) -> dict:
        r = requests.post(f"{self.url}/api/v1{path}", headers=self.headers,
                          json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_artists(self) -> list[dict]:
        return self._get("/artist")

    def get_quality_profiles(self) -> list[dict]:
        return self._get("/qualityprofile")

    def get_metadata_profiles(self) -> list[dict]:
        return self._get("/metadataprofile")

    def lookup_artist(self, term: str) -> list[dict]:
        return self._get("/artist/lookup", term=term)

    def add_artist(self, mb_artist: dict, quality_id: int, metadata_id: int) -> dict:
        monitored = LIDARR_MONITOR_MODE != "none"
        search_missing = LIDARR_MONITOR_MODE == "all"
        payload = {
            "foreignArtistId": mb_artist["foreignArtistId"],
            "artistName": mb_artist["artistName"],
            "qualityProfileId": quality_id,
            "metadataProfileId": metadata_id,
            "rootFolderPath": LIDARR_ROOT_FOLDER,
            "monitored": monitored,
            "addOptions": {
                "monitor": LIDARR_MONITOR_MODE,
                "searchForMissingAlbums": search_missing,
            },
        }
        return self._post("/artist", payload)


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------
def resolve_profile_id(profiles: list[dict], name: str, label: str) -> int:
    if not name:
        pid = profiles[0]["id"]
        log.info("  %s profile not set — using first: '%s' (id=%d)",
                 label, profiles[0]["name"], pid)
        return pid
    for p in profiles:
        if p["name"].lower() == name.lower():
            return p["id"]
    raise ValueError(f"{label} profile '{name}' not found. "
                     f"Available: {[p['name'] for p in profiles]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if DRY_RUN:
        log.info("=" * 60)
        log.info("DRY RUN — no artists will be added to Lidarr")
        log.info("=" * 60)

    max_label = str(MAX_OVERLAP_SCORE) if MAX_OVERLAP_SCORE else "unlimited"
    log.info("Overlap window: %d – %s  |  Monitor: %s  |  Cache TTL: %d days",
             MIN_OVERLAP_SCORE, max_label, LIDARR_MONITOR_MODE, CACHE_TTL_DAYS)

    lidarr = LidarrClient(LIDARR_URL, LIDARR_API_KEY)
    quality_id = resolve_profile_id(lidarr.get_quality_profiles(), LIDARR_QUALITY_PROFILE, "Quality")
    metadata_id = resolve_profile_id(lidarr.get_metadata_profiles(), LIDARR_METADATA_PROFILE, "Metadata")

    cache = load_cache()

    # Evict expired entries before run
    evicted = evict_expired(cache)
    if evicted:
        log.info("Cache: evicted %d expired entries (TTL=%d days)", evicted, CACHE_TTL_DAYS)

    log.info("Fetching artists from Lidarr...")
    lidarr_artists = lidarr.get_artists()
    known_mbids = {a["foreignArtistId"] for a in lidarr_artists if a.get("foreignArtistId")}
    known_names_lower = {a["artistName"].lower() for a in lidarr_artists}
    seed_mbids = [a["foreignArtistId"] for a in lidarr_artists if a.get("foreignArtistId")]
    log.info("Found %d artists in Lidarr (%d with MusicBrainz IDs)",
             len(lidarr_artists), len(seed_mbids))

    log.info("Querying ListenBrainz Labs (depth=1)...")
    lb_results = lb_similar_all(seed_mbids, cache)
    save_cache(cache)

    candidate_scores: dict[str, int] = {}
    candidate_weight: dict[str, float] = {}
    candidate_names: dict[str, str] = {}
    depth1_mbids: set[str] = set()

    for seed_mbid, similar in lb_results.items():
        for s in similar:
            cmbid = s["mbid"]
            if not cmbid or cmbid in known_mbids:
                continue
            candidate_scores[cmbid] = candidate_scores.get(cmbid, 0) + 1
            candidate_weight[cmbid] = candidate_weight.get(cmbid, 0.0) + s["score"]
            candidate_names[cmbid] = s["name"]
            depth1_mbids.add(cmbid)

    log.info("Depth 1 complete: %d unique candidates found", len(candidate_scores))

    if DISCOVERY_DEPTH >= 2:
        log.info("Querying ListenBrainz Labs (depth=2)...")
        depth2_seeds = [
            mbid for mbid in depth1_mbids
            if candidate_scores.get(mbid, 0) >= max(1, MIN_OVERLAP_SCORE - 1)
        ]
        log.info("  %d promising depth-1 candidates to expand...", len(depth2_seeds))
        lb_results2 = lb_similar_all(depth2_seeds, cache)
        save_cache(cache)
        for seed_mbid, similar in lb_results2.items():
            for s in similar:
                cmbid = s["mbid"]
                if not cmbid or cmbid in known_mbids:
                    continue
                candidate_scores[cmbid] = candidate_scores.get(cmbid, 0) + 1
                candidate_weight[cmbid] = candidate_weight.get(cmbid, 0.0) + s["score"]
                candidate_names[cmbid] = s["name"]

    ranked = sorted(
        candidate_scores.items(),
        key=lambda x: (x[1], candidate_weight.get(x[0], 0.0)),
        reverse=True,
    )
    filtered = [
        (mbid, score) for mbid, score in ranked
        if score >= MIN_OVERLAP_SCORE
        and (MAX_OVERLAP_SCORE == 0 or score <= MAX_OVERLAP_SCORE)
    ]

    log.info("Candidates in overlap window [%d–%s]: %d total",
             MIN_OVERLAP_SCORE, max_label, len(filtered))
    log.info("Top 20 candidates:")
    for mbid, score in filtered[:20]:
        weight = candidate_weight.get(mbid, 0.0)
        name = candidate_names.get(mbid, mbid)
        log.info("  [overlap=%3d  weight=%8.0f]  %s", score, weight, name)

    added = 0
    skipped = 0

    for mbid, score in filtered:
        if added >= MAX_ADD:
            break

        artist_name = candidate_names.get(mbid, mbid)
        mb_results = lidarr.lookup_artist(f"lidarr:{mbid}")
        if not mb_results:
            mb_results = lidarr.lookup_artist(artist_name)
        if not mb_results:
            log.warning("  ✗ Not found in MusicBrainz: %s (%s)", artist_name, mbid)
            skipped += 1
            continue

        if mb_results[0]["artistName"].lower() in known_names_lower:
            log.debug("  Already in Lidarr: %s", artist_name)
            continue

        if DRY_RUN:
            log.info("  [DRY RUN] Would add: %s (overlap=%d, monitor=%s)",
                     artist_name, score, LIDARR_MONITOR_MODE)
            added += 1
            continue

        try:
            lidarr.add_artist(mb_results[0], quality_id, metadata_id)
            log.info("  ✓ Added: %s (overlap=%d, monitor=%s)",
                     artist_name, score, LIDARR_MONITOR_MODE)
            added += 1
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 400:
                log.debug("  Already exists in Lidarr: %s", artist_name)
            else:
                log.warning("  ✗ Failed to add %s: %s", artist_name, exc)
                skipped += 1
        time.sleep(0.3)

    log.info("Done. Added: %d  Skipped: %d", added, skipped)


if __name__ == "__main__":
    main()
