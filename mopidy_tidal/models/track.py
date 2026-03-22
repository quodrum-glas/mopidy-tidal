from __future__ import annotations

import mopidy.models as mm
import tidalapi as tdl

from mopidy_tidal.cache import cache_by_uri, cached_by_uri
from mopidy_tidal.display import track_display_name
from mopidy_tidal.uri import URI, URIType

from ._base import IMAGE_SIZE, Model, _year_from
from .album import Album
from .artist import Artist


class Track(Model):
    @classmethod
    @cache_by_uri
    def from_api(cls, track: tdl.Track) -> Track:
        uri = URI(URIType.TRACK, track.id)
        return cls(
            ref=mm.Ref.track(uri=str(uri), name=track_display_name(track)),
            api=track,
            artists=[Artist.from_api(a) for a in track.artists],
            album=Album.from_api(track.album) if track.album else None,
        )

    @classmethod
    @cached_by_uri
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Track:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.TRACK:
            raise ValueError(f"Not a valid uri for Track: {uri}")
        track = session.track(parsed.track)
        return cls(
            ref=mm.Ref.track(uri=str(parsed), name=track_display_name(track)),
            api=track,
            artists=[Artist.from_api(a) for a in track.artists],
            album=Album.from_api(track.album) if track.album else None,
        )

    def items(self) -> list:
        raise AttributeError

    def tracks(self) -> list[Track]:
        return [self]

    def radio(self) -> list[Track]:
        return [
            Track.from_api(t)
            for t in self.api.similar()
            if isinstance(t, tdl.Track)
        ]

    def build(self) -> mm.Track:
        album_date = _year_from(self.api.album.release_date) if self.api.album else None
        return mm.Track(
            uri=self.uri,
            name=self.name,
            track_no=self.api.track_num,
            artists=[a.full for a in self.artists],
            album=self.album.full if self.album else None,
            length=self.api.duration * 1000,
            date=album_date,
            disc_no=self.api.volume_num,
            genre=self.api.audio_quality,
            comment=" ".join(map(str, self.api.media_metadata_tags)),
        )

    @property
    def images(self) -> list[mm.Image]:
        return [
            *(self.album.images if self.album else []),
            *(img for a in self.artists for img in a.images),
        ]
