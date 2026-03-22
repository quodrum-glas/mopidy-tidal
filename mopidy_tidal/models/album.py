from __future__ import annotations

from typing import TYPE_CHECKING

import mopidy.models as mm
import tidalapi as tdl

from mopidy_tidal.cache import cache_by_uri, cached_by_uri
from mopidy_tidal.uri import URI, URIType

from ._base import IMAGE_SIZE, Model, _year_from
from .artist import Artist

if TYPE_CHECKING:
    from .track import Track


class Album(Model):
    @classmethod
    @cache_by_uri
    def from_api(cls, album: tdl.Album) -> Album:
        uri = URI(URIType.ALBUM, album.id)
        return cls(
            ref=mm.Ref.album(uri=str(uri), name=album.name),
            api=album,
            artists=[Artist.from_api(a) for a in album.artists],
        )

    @classmethod
    @cached_by_uri
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Album:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.ALBUM:
            raise ValueError(f"Not a valid uri for Album: {uri}")
        album = session.album(parsed.album)
        return cls(
            ref=mm.Ref.album(uri=str(parsed), name=album.name),
            api=album,
            artists=[Artist.from_api(a) for a in album.artists],
        )

    def build(self) -> mm.Album:
        return mm.Album(
            uri=self.uri,
            name=self.name,
            artists=[a.full for a in self.artists],
            num_tracks=self.api.num_tracks,
            num_discs=self.api.num_volumes,
            date=_year_from(self.api.release_date),
        )

    def items(self) -> list[Model]:
        from .containers import Future

        return [
            Future.from_api(self.api.get_page, ref_type=mm.Ref.DIRECTORY, title=f"Page: {self.name}"),
            *self.tracks(),
        ]

    def tracks(self) -> list[Track]:
        from .track import Track

        return [Track.from_api(t) for t in self.api.tracks()]

    @property
    def images(self) -> list[mm.Image]:
        image_uri = self.api.image(IMAGE_SIZE)
        return [mm.Image(uri=image_uri, width=IMAGE_SIZE, height=IMAGE_SIZE)] if image_uri else []
