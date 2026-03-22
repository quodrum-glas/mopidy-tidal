from __future__ import annotations

from typing import TYPE_CHECKING

import mopidy.models as mm
import tidalapi as tdl

from mopidy_tidal.cache import cache_by_uri, cached_by_uri
from mopidy_tidal.uri import URI, URIType

from ._base import IMAGE_SIZE, Model

if TYPE_CHECKING:
    from .track import Track


class Artist(Model):
    @classmethod
    @cache_by_uri
    def from_api(cls, artist: tdl.Artist) -> Artist:
        uri = URI(URIType.ARTIST, artist.id)
        return cls(ref=mm.Ref.artist(uri=str(uri), name=artist.name), api=artist)

    @classmethod
    @cached_by_uri
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Artist:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.ARTIST:
            raise ValueError(f"Not a valid uri for Artist: {uri}")
        artist = session.artist(parsed.artist)
        return cls(ref=mm.Ref.artist(uri=str(parsed), name=artist.name), api=artist)

    def build(self) -> mm.Artist:
        return mm.Artist(uri=self.uri, name=self.name)

    def items(self) -> list[Model]:
        from .album import Album
        from .containers import Future

        return [
            Future.from_api(self.api.get_page, ref_type=mm.Ref.DIRECTORY, title=f"Page: {self.name}"),
            Future.from_api(self.api.similar, ref_type=mm.Ref.DIRECTORY, title=f"Similar: {self.name}"),
            Future.from_api(self.api.radio, ref_type=mm.Ref.PLAYLIST, title=f"Radio: {self.name}"),
            *self.tracks(),
            *(Album.from_api(a) for a in self.api.get_albums()),
        ]

    def tracks(self, limit: int = 10) -> list[Track]:
        from .track import Track

        return [Track.from_api(t) for t in self.api.get_top_tracks(limit=limit)]

    @property
    def images(self) -> list[mm.Image]:
        image_uri = self.api.image(IMAGE_SIZE)
        return [mm.Image(uri=image_uri, width=IMAGE_SIZE, height=IMAGE_SIZE)] if image_uri else []
