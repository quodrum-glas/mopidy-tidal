from __future__ import annotations

from typing import TYPE_CHECKING

from mopidy.models import Artist as MopidyArtist, Image as MopidyImage, Ref as MopidyRef
from tidalapi import Session as TidalSession
from tidalapi.models import Artist as TidalArtist
from tidalapi.models_v1 import Artist as TidalArtistV1

from mopidy_tidal.cache import cached_by_uri
from mopidy_tidal.uri import URI, URIType

from ._base import IMAGE_SIZE, Model

if TYPE_CHECKING:
    from .track import Track


class Artist(Model):
    @classmethod
    def from_api(cls, artist: TidalArtist | TidalArtistV1) -> Artist:
        """From any tidal artist model (v1 or oapi)."""
        uri = URI(URIType.ARTIST, artist.id)
        return cls(ref=MopidyRef.artist(uri=str(uri), name=artist.name), api=artist)

    @classmethod
    @cached_by_uri
    def _from_uri(cls, session: TidalSession, /, *, uri: str) -> Artist:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.ARTIST:
            raise ValueError(f"Not a valid uri for Artist: {uri}")
        return cls.from_api(session.artist(parsed.artist))

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Artist:
        model = cls._from_uri(session, uri=uri)
        model.session = session
        return model

    def build(self) -> MopidyArtist:
        return MopidyArtist(uri=self.uri, name=self.name)

    def items(self) -> list[Model]:
        from .album import Album
        from .containers import Future

        result: list[Model] = []
        if self.session:
            result.append(Future.from_v1(
                lambda: self.session.get_artist_page(int(self.api.id)),
                ref_type=MopidyRef.DIRECTORY, title=f"Page: {self.name}"))
            result.append(Future.from_v1(
                lambda: self.api.similar_artists,
                ref_type=MopidyRef.DIRECTORY, title=f"Similar: {self.name}"))

        # Radio playlists
        for p in self.api.radio:
            from .playlist import Playlist
            mp = Playlist.from_api(p)
            mp.ref = mp.ref.replace(name=f"Radio: {mp.name}")
            result.append(mp)

        result.extend(self.tracks())

        if self.session:
            result.extend(Album.from_api(a) for a in self.session.get_artist_albums(int(self.api.id)))
        else:
            result.extend(Album.from_api(a) for a in self.api.albums)

        return result

    def tracks(self, limit: int = 20) -> list[Track]:
        from .track import Track
        if self.session:
            return [Track.from_api(t) for t in self.session.get_artist_tracks(int(self.api.id), limit=limit)]
        return [Track.from_api(t) for t in self.api.get_top_tracks(limit=limit)]

    @property
    def images(self) -> list[MopidyImage]:
        url = self.api.profile(IMAGE_SIZE)
        return [MopidyImage(uri=url, width=IMAGE_SIZE, height=IMAGE_SIZE)] if url else []
