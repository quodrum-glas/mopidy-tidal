from __future__ import annotations

import logging

from mopidy.models import Image as MopidyImage, Ref as MopidyRef, Track as MopidyTrack
from tidalapi import Session as TidalSession
from tidalapi.models import Track as TidalTrack
from tidalapi.models_v1 import Track as TidalTrackV1

from mopidy_tidal.cache import cache_by_uri_if, cached_by_uri
from mopidy_tidal.display import track_display_name, track_quality
from mopidy_tidal.uri import URI, URIType

from ._base import Model, _year_from

logger = logging.getLogger(__name__)


class Track(Model):
    @classmethod
    @cache_by_uri_if(lambda result: getattr(result.api, 'artists', None))
    def from_api(cls, track: TidalTrack | TidalTrackV1, **kwargs) -> Track:
        """From any tidal track model (v1 or oapi). Cached only if complete."""
        uri = URI(URIType.TRACK, track.id)
        return cls(
            ref=MopidyRef.track(uri=str(uri), name=track.name),
            api=track,
            **kwargs,
        )

    @classmethod
    @cached_by_uri
    def _from_uri(cls, session: TidalSession, /, *, uri: str) -> Track:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.TRACK:
            raise ValueError(f"Not a valid uri for Track: {uri}")
        return cls.from_api(session.track(parsed.track))

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Track:
        """Fetch by URI with cache. Always returns a fully-hydrated track."""
        model = cls._from_uri(session, uri=uri)
        model.session = session
        return model

    @property
    def artists(self) -> list:
        from .artist import Artist
        return [Artist.from_api(a) for a in self.api.artists]

    @property
    def album(self):
        from .album import Album
        return self.__dict__.get('album') or (
            Album.from_api(self.api.album) if self.api.album else None
        )

    def items(self) -> list:
        raise AttributeError

    def tracks(self) -> list[Track]:
        return [self]

    def radio(self) -> list[Track]:
        return [Track.from_api(t) for t in self.api.similar_tracks]

    def build(self) -> MopidyTrack:
        api = self.api
        album_date = _year_from(api.album.release_date) if api.album else None
        audio_quality = track_quality(api)

        return MopidyTrack(
            uri=self.uri,
            name=track_display_name(api),
            track_no=api.track_num,
            artists=[a.full for a in self.artists],
            album=self.album.full if self.album else None,
            length=api.duration * 1000,
            date=album_date,
            disc_no=api.volume_num,
            genre=audio_quality,
            comment=audio_quality,
        )

    @property
    def images(self) -> list[MopidyImage]:
        return [
            *(self.album.images if self.album else []),
            *(img for a in self.artists for img in a.images),
        ]
