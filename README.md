# Mopidy-Tidal

Mopidy extension for Tidal music service integration.

This is a fork of [tehkillerbee/mopidy-tidal](https://github.com/tehkillerbee/mopidy-tidal), referenced from the [Mopidy documentation](https://docs.mopidy.com/).

Maintained by [quodrum-glas](https://github.com/quodrum-glas).

## Installation

Requires Python >= 3.10, Mopidy >= 3.0, and GStreamer (including bad plugins for m4a playback).

### From git
```
pip install 'git+https://github.com/quodrum-glas/mopidy-tidal.git'
```

### Development setup (Arch Linux)

System dependencies and editable install:
```bash
sudo ./install-dependencies.sh
sudo ./install-dev-packages.sh
```

## Dependencies

- [tidalapi](https://github.com/quodrum-glas/python-tidal) — bundled Tidal API client (also a fork)
- GStreamer bad plugins — required for m4a/AAC streams

## Configuration

Add to your Mopidy configuration (usually `/etc/mopidy/mopidy.conf`):
```ini
[tidal]
enabled = true
quality = LOSSLESS
client_id =
client_secret =
widevine_cdm_path =
fetch_album_covers = false
playlist_cache_refresh_secs = 300
pagination_max_results = 40
login_web_port = 8989
http_timeout = 3.05, 1.5
```

**quality:** `HI_RES_LOSSLESS`, `LOSSLESS`, `HIGH`, or `LOW`. Must match your subscription tier. `HI_RES_LOSSLESS` is only available with PKCE login (client_id only, no client_secret).

**widevine_cdm_path:** Path to a `.wvd` device file for DRM playback. Works with all quality levels. Non-DRM playback may stop working in the future.

**playlist_cache_refresh_secs:** How long (seconds) a cached playlist is considered valid. `0` = never refresh automatically. Default `300`.

**login_web_port:** Port for the OAuth login page.

### OAuth Login

On startup, the extension displays a URL to visit for login. Authentication is non-blocking — Mopidy continues to load. Once login completes, the library updates to the online library.