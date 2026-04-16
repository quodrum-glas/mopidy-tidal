from __future__ import annotations

import logging

from mopidy.models import Album as MopidyAlbum, Image as MopidyImage, Playlist as MopidyPlaylist, Ref as MopidyRef
from tidalapi import Session as TidalSession
from tidalapi.models import Playlist as TidalPlaylist
from tidalapi.models_v1 import Playlist as TidalPlaylistV1, Track as TidalTrackV1

from mopidy_tidal.cache import cached_items
from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType

from ._base import IMAGE_SIZE, Model, _year_from
from .artist import Artist
from .track import Track

logger = logging.getLogger(__name__)

class Playlist(Model):
    @classmethod
    def from_api(cls, playlist: TidalPlaylist | TidalPlaylistV1) -> Playlist:
        """From any tidal playlist model (v1 preferred, oapi for exception)."""
        uri = URI(URIType.PLAYLIST, playlist.id)
        return cls(
            ref=MopidyRef.playlist(uri=str(uri), name=playlist.name),
            api=playlist,
        )

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Playlist:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.PLAYLIST:
            raise ValueError(f"Not a valid uri for Playlist: {uri}")
        playlist = session.playlist(parsed.playlist)
        return cls(
            ref=MopidyRef.playlist(uri=str(parsed), name=playlist.name),
            api=playlist,
            session=session,
        )

    @property
    def last_modified(self) -> int:
        return to_timestamp(self.api.last_updated)

    def build(self) -> MopidyPlaylist:
        return MopidyPlaylist(
            uri=self.uri,
            name=self.name,
            tracks=[t.full for t in self.items()],
            last_modified=self.last_modified,
        )

    def items(self) -> list[Track]:
        return self.tracks()

    @cached_items
    def tracks(self) -> list[Track]:
        if self.session:
            return [Track.from_api(t) for t in self.session.get_playlist_tracks(str(self.api.id))]
        return [Track.from_api(t) for t in self.api.tracks]

    @property
    def images(self) -> list[MopidyImage]:
        url = self.api.cover(IMAGE_SIZE)
        return [MopidyImage(uri=url, width=IMAGE_SIZE, height=IMAGE_SIZE)] if url else []


class PlaylistAsAlbum(Model):
    """Wraps a TIDAL Playlist as a Mopidy Album so it appears in search results."""

    @classmethod
    def from_api(cls, playlist: TidalPlaylistV1) -> PlaylistAsAlbum:
        uri = URI(URIType.PLAYLIST, playlist.id)
        return cls(
            ref=MopidyRef.album(uri=str(uri), name=playlist.name),
            api=playlist,
        )

    def build(self) -> MopidyAlbum:
        return MopidyAlbum(
            uri=self.uri,
            name=self.name,
        )

    def items(self) -> list[Model]:
        return self.tracks()

    def tracks(self) -> list[Track]:
        return [Track.from_api(t) for t in self.api.tracks()]

    @property
    def images(self) -> list[MopidyImage]:
        image_uri = self.api.cover(IMAGE_SIZE)
        return [MopidyImage(uri=image_uri, width=IMAGE_SIZE, height=IMAGE_SIZE)] if image_uri else []
