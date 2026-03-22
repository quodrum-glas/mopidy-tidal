from __future__ import annotations

import mopidy.models as mm
import tidalapi as tdl

from mopidy_tidal.cache import cached_items
from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType
from mopidy_tidal.workers import paginated

from ._base import IMAGE_SIZE, Model, _year_from
from .artist import Artist
from .track import Track


class Playlist(Model):
    @classmethod
    def from_api(cls, playlist: tdl.Playlist) -> Playlist:
        uri = URI(URIType.PLAYLIST, playlist.id)
        return cls(
            ref=mm.Ref.playlist(uri=str(uri), name=playlist.name),
            api=playlist,
        )

    @classmethod
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Playlist:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.PLAYLIST:
            raise ValueError(f"Not a valid uri for Playlist: {uri}")
        playlist = session.playlist(parsed.playlist)
        return cls(
            ref=mm.Ref.playlist(uri=str(parsed), name=playlist.name),
            api=playlist,
        )

    @property
    def last_modified(self) -> int:
        return to_timestamp(self.api.last_updated)

    def build(self) -> mm.Playlist:
        return mm.Playlist(
            uri=self.uri,
            name=self.name,
            tracks=[t.full for t in self.items()],
            last_modified=self.last_modified,
        )

    def items(self) -> list[Track]:
        return self.tracks()

    @cached_items
    def tracks(self) -> list[Track]:
        return [
            Track.from_api(item)
            for page in paginated(self.api.tracks, total=self.api.num_tracks)
            for item in page
            if isinstance(item, tdl.Track)
        ]

    @property
    def images(self) -> list[mm.Image]:
        image_uri = self.api.image(IMAGE_SIZE)
        return [mm.Image(uri=image_uri, width=IMAGE_SIZE, height=IMAGE_SIZE)] if image_uri else []


class PlaylistAsAlbum(Model):
    """Wraps a TIDAL Playlist as a Mopidy Album so it appears in search results."""

    @classmethod
    def from_api(cls, playlist: tdl.Playlist) -> PlaylistAsAlbum:
        uri = URI(URIType.PLAYLIST, playlist.id)
        return cls(
            ref=mm.Ref.album(uri=str(uri), name=playlist.name),
            api=playlist,
        )

    def build(self) -> mm.Album:
        return mm.Album(
            uri=self.uri,
            name=self.name,
            artists=[Artist.from_api(a).full for a in self.api.promoted_artists or []],
            num_tracks=self.api.num_tracks,
            date=_year_from(self.api.created),
        )

    def items(self) -> list[Model]:
        return self.tracks()

    def tracks(self) -> list[Track]:
        return [Track.from_api(t) for t in self.api.tracks()]

    @property
    def images(self) -> list[mm.Image]:
        image_uri = self.api.image(IMAGE_SIZE)
        return [mm.Image(uri=image_uri, width=IMAGE_SIZE, height=IMAGE_SIZE)] if image_uri else []
