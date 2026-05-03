#!/usr/bin/env python3
"""Standalone integration test: verify mopidy-tidal loads as a Mopidy extension."""
from __future__ import annotations

import sys


def main() -> int:
    # 1. Extension class loads
    from mopidy_tidal import Extension

    ext = Extension()
    print(f"OK: Extension loaded — {ext.dist_name} {ext.version}")

    # 2. Default config parses
    config = ext.get_default_config()
    assert "[tidal]" in config, "Default config missing [tidal] section"
    print(f"OK: Default config parsed ({len(config)} chars)")

    # 3. Config schema has expected keys
    schema = ext.get_config_schema()
    expected = {"quality", "client_id", "client_secret", "playlist_cache_refresh_secs",
                "pagination_max_results", "login_web_port", "http_timeout"}
    missing = expected - set(schema.keys())
    assert not missing, f"Config schema missing keys: {missing}"
    print(f"OK: Config schema has {len(schema)} keys")

    # 4. Backend class is importable
    from mopidy_tidal.backend import TidalBackend
    print(f"OK: TidalBackend importable")

    # 5. All provider classes importable
    from mopidy_tidal.library import TidalLibraryProvider
    from mopidy_tidal.playback import TidalPlaybackProvider
    from mopidy_tidal.playlists import TidalPlaylistsProvider
    print("OK: All providers importable")

    print("\nAll integration checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
