from __future__ import annotations

from typing import TYPE_CHECKING

from mopidy.models import Album as MopidyAlbum, Image as MopidyImage, Ref as MopidyRef
from tidalapi import Session as TidalSession
from tidalapi.models import Album as TidalAlbum
from tidalapi.models_v1 import Album as TidalAlbumV1

from mopidy_tidal.cache import cached_by_uri
from mopidy_tidal.uri import URI, URIType

from ._base import IMAGE_SIZE, Model, _year_from
from .artist import Artist

if TYPE_CHECKING:
    from .track import Track


class Album(Model):
    @classmethod
    def from_api(cls, album: TidalAlbum | TidalAlbumV1) -> Album:
        """From any tidal album model (v1 or oapi)."""
        uri = URI(URIType.ALBUM, album.id)
        return cls(
            ref=MopidyRef.album(uri=str(uri), name=album.name),
            api=album,
        )

    @classmethod
    @cached_by_uri
    def _from_uri(cls, session: TidalSession, /, *, uri: str) -> Album:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.ALBUM:
            raise ValueError(f"Not a valid uri for Album: {uri}")
        return cls.from_api(session.album(parsed.album))

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Album:
        model = cls._from_uri(session, uri=uri)
        model.session = session
        return model

    @property
    def artists(self) -> list[Artist]:
        return [Artist.from_api(a) for a in self.api.artists]

    def build(self) -> MopidyAlbum:
        api = self.api
        return MopidyAlbum(
            uri=self.uri,
            name=self.name,
            artists=[a.full for a in self.artists],
            num_tracks=api.num_tracks,
            num_discs=api.num_volumes,
            date=_year_from(api.release_date),
        )

    def items(self) -> list[Model]:
        from .containers import Future

        result: list[Model] = []
        if self.session:
            result.append(Future.from_v1(
                lambda: self.session.get_album_page(int(self.api.id)),
                ref_type=MopidyRef.DIRECTORY, title=f"Page: {self.name}"))
            if self.artists:
                result.extend(
                    Future.from_v1(
                        lambda aid=int(a.api.id): self.session.get_artist_page(aid),
                        ref_type=MopidyRef.DIRECTORY, title=f"Artist: {a.name}")
                    for a in self.artists
                )
            result.append(Future.from_v1(
                lambda: self.api.similar_albums,
                ref_type=MopidyRef.DIRECTORY, title=f"Similar: {self.name}"))

        result.extend(self.tracks())
        return result

    def tracks(self) -> list[Track]:
        from .track import Track
        if self.session:
            return [Track.from_api(t, album=self) for t in self.session.get_album_tracks(int(self.api.id))]
        return [Track.from_api(t) for t in self.api.tracks]

    @property
    def images(self) -> list[MopidyImage]:
        url = self.api.cover(IMAGE_SIZE)
        return [MopidyImage(uri=url, width=IMAGE_SIZE, height=IMAGE_SIZE)] if url else []
