# Lidarr ListenBrainz Discovery

Discovers new artists via [ListenBrainz](https://listenbrainz.org) Similar Artists
API and adds them to Lidarr.

## Why ListenBrainz

- **Free, no API key required** — open source project by MetaBrainz Foundation.
- **Direct MusicBrainz ID integration** — Lidarr already stores MusicBrainz IDs
  for every artist. ListenBrainz uses the same IDs. No intermediate lookup needed.
- **Community listening data** — similarity is based on actual listening patterns,
  not just metadata tags.

## How it works

1. Fetches all artists from Lidarr (each has a MusicBrainz ID).
2. Calls `ListenBrainz /1/similar-artists/{mbid}` for each artist.
3. Scores each candidate by **overlap**: how many of your artists list it as similar.
   Also tracks cumulative **similarity weight** as a tiebreaker.
4. Optionally goes one level deeper (`DISCOVERY_DEPTH=2`).
5. Ranks by overlap score, filters by `MIN_OVERLAP_SCORE`.
6. Looks up top candidates in Lidarr by MusicBrainz ID and adds them.

An overlap score of 3 means three of your artists independently
recommend the same new artist — a strong relevance signal.

## Setup

### 1. Lidarr API key

Settings → General → Security → API Key

### 2. Configure

```bash
cp .env.example .env
# Edit .env — fill in LIDARR_URL and LIDARR_API_KEY
```

### 3. Build

```bash
docker compose build
```

### 4. Dry run first

```bash
# DRY_RUN=true is the default in .env.example
docker compose run --rm lidarr-discovery
```

Review the candidate list. Adjust `MIN_OVERLAP_SCORE` and `MAX_ADD` as needed.

### 5. Real run

```bash
# Set DRY_RUN=false in .env
docker compose run --rm lidarr-discovery
```

### 6. Schedule via Unraid User Scripts

Add a new User Script with this content, set schedule (e.g. weekly):

```bash
#!/bin/bash
cd /mnt/user/appdata/compose/lidarr-discovery
docker compose run --rm lidarr-discovery
```

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `LIDARR_URL` | required | e.g. `http://192.168.10.10:8686` |
| `LIDARR_API_KEY` | required | Lidarr API key |
| `LIDARR_ROOT_FOLDER` | `/music` | Root folder for new artists |
| `LIDARR_QUALITY_PROFILE` | first | Quality profile name |
| `LIDARR_METADATA_PROFILE` | first | Metadata profile name |
| `LIDARR_MONITOR` | `false` | Monitor added artists immediately |
| `DISCOVERY_DEPTH` | `1` | `1` or `2` |
| `MIN_OVERLAP_SCORE` | `2` | Minimum overlap count |
| `MAX_SIMILAR_PER_ARTIST` | `20` | Similar artists fetched per artist |
| `MIN_SIMILARITY` | `0.25` | Minimum ListenBrainz similarity score (0.0–1.0) |
| `MAX_ADD` | `10` | Max artists added per run |
| `DRY_RUN` | `false` | Log only, do not add |

## Notes

- Added artists are **unmonitored** by default. Review them in Lidarr
  and manually monitor the ones you want downloaded.
- ListenBrainz API results are **cached** in `/app/data/cache.json`.
  Subsequent runs are faster and cause less load on the API.
- If your library is small (< 50 artists), try `MIN_OVERLAP_SCORE=1`.
- Cache is per MusicBrainz ID — safe to delete and rebuild at any time.
