from __future__ import unicode_literals

import logging
from pathlib import Path

from cachetools import TTLCache, cachedmethod
from mopidy import backend
from mopidy_tidal.helpers import Catch, Throttle
from mopidy_tidal.uri import URI

from tidalapi.media import ManifestMimeType
from tidalapi.exceptions import ObjectNotFound

logger = logging.getLogger(__name__)


class TidalPlaybackProvider(backend.PlaybackProvider):

    __cache = TTLCache(maxsize=128, ttl=120)

    @cachedmethod(lambda slf: slf.__cache)
    @Catch(ObjectNotFound)
    @Throttle(calls=2, interval=2)
    def translate_uri(self, uri):
        logger.debug("TidalPlaybackProvider translate_uri: %s", uri)
        track = self.backend.session.track(URI.from_string(uri).track)
        stream = track.get_stream()
        manifest = stream.get_stream_manifest()
        logger.info("%s %ibit/%iHz %s %s : %s", stream.manifest_mime_type, stream.bit_depth, stream.sample_rate,
                    stream.audio_quality, manifest.get_codecs(), track.full_name)

        if stream.manifest_mime_type == ManifestMimeType.MPD.value:
            data = stream.get_manifest_data()
            if data:
                mpd_path = Path(
                    self.backend.get_dir("cache"), "manifest.mpd"
                )
                with open(mpd_path, "w") as file:
                    file.write(data)

                return "file://{}".format(mpd_path)
            else:
                raise AttributeError("No MPD manifest available!")
        elif stream.manifest_mime_type == ManifestMimeType.BTS.value:
            return manifest.get_urls()
