from __future__ import annotations

"""Playback provider: translates tidal:// URIs into playable URLs."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

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

        logger.debug(
            "Playback: track=%s quality=%s codec=%s %dbit/%dHz drm=%s",
            track_id, stream.audio_quality, stream.codec,
            stream.bit_depth, stream.sample_rate, stream.drm_system or "none",
        )

        if stream.is_drm:
            return self._translate_drm(stream)

        if stream.is_mpd:
            return self._translate_mpd(stream)

        if stream.is_bts:
            return self._translate_bts(stream)

        logger.warning("Unknown manifest type: %s", stream.manifest_mime_type)
        return None

    def _translate_drm(self, stream) -> str | None:
        """Decrypt Widevine DASH stream and return HTTP URL for GStreamer."""
        from mopidy_tidal.drm import decrypt_stream

        keys = self.backend.session.get_decryption_keys(stream)
        return decrypt_stream(stream, keys)

    def _translate_mpd(self, stream) -> str | None:
        mpd_xml = stream.get_manifest_data()
        if not mpd_xml:
            raise ValueError("No MPD manifest available")
        mpd_path = Path(
            self.backend.cache_dir,
            f"manifest_{self.n % self.MAX_CACHE_MANIFEST_FILES}.mpd",
        )
        mpd_path.write_text(mpd_xml)
        self.n += 1
        return f"file://{mpd_path}"

    def _translate_bts(self, stream) -> str | None:
        manifest = stream.get_stream_manifest()
        if manifest:
            urls = manifest.get_urls()
            return urls[0] if urls else None
        return None
