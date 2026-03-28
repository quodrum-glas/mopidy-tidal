from __future__ import annotations

from typing import TYPE_CHECKING, cast

"""Playback provider: translates tidal:// URIs into playable URLs."""

import logging
from pathlib import Path

from cachetools import TTLCache, cachedmethod
from mopidy.backend import PlaybackProvider

from mopidy_tidal.helpers import backoff_on_error
from mopidy_tidal.uri import URI

if TYPE_CHECKING:
    from mopidy_tidal.backend import TidalBackend

logger = logging.getLogger(__name__)


class TidalPlaybackProvider(PlaybackProvider):

    MAX_CACHE_MANIFEST_FILES = 5

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.__cache: TTLCache = TTLCache(maxsize=128, ttl=120)
        self.backend = cast("TidalBackend", self.backend)
        self.n = 0

    @cachedmethod(lambda self: self.__cache)
    @backoff_on_error(seconds=5.0)
    def translate_uri(self, uri: str) -> str | None:
        track_id = URI.from_string(uri).track
        stream = self.backend.session.get_stream(track_id, self.backend.quality)

        logger.info(
            "Playback: track=%s quality=%s codec=%s %dbit/%dHz",
            track_id, stream.audio_quality, stream.codec,
            stream.bit_depth, stream.sample_rate,
        )

        if stream.is_mpd:
            mpd_xml = stream.get_manifest_data()
            if not mpd_xml:
                raise ValueError("No MPD manifest available")
            mpd_path = Path(self.backend.cache_dir, f"manifest_{self.n % self.MAX_CACHE_MANIFEST_FILES}.mpd")
            mpd_path.write_text(mpd_xml)
            self.n += 1
            return f"file://{mpd_path}"

        if stream.is_bts:
            manifest = stream.get_stream_manifest()
            if manifest:
                urls = manifest.get_urls()
                return urls[0] if urls else None
            return None

        logger.warning("Unknown manifest type: %s", stream.manifest_mime_type)
        return None
