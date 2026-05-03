from __future__ import annotations

from mopidy.models import Image as MopidyImage
from mopidy.models import Playlist as MopidyPlaylist
from mopidy.models import Ref as MopidyRef
from tidalapi import Session as TidalSession
from tidalapi.models_v1 import Mix as TidalMixV1
from tidalapi.models_v1 import Track as TidalTrackV1

from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType

from ._base import Model
from .track import Track


class Mix(Model):
    @classmethod
    def from_api(cls, mix: TidalMixV1) -> Mix:
        uri = URI(URIType.MIX, mix.id)
        return cls(
            ref=MopidyRef.playlist(uri=str(uri), name=f"{mix.title} ({mix.sub_title})"),
            api=mix,
        )

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Mix:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.MIX:
            raise ValueError(f"Not a valid uri for Mix: {uri}")
        mix = session.mix(parsed.mix)
        return cls(
            ref=MopidyRef.playlist(uri=str(parsed), name=f"{mix.title} ({mix.sub_title})"),
            api=mix,
        )

    @property
    def last_modified(self) -> int:
        return to_timestamp(self.api.updated)

    def build(self) -> MopidyPlaylist:
        return MopidyPlaylist(
            uri=self.uri,
            name=self.name,
            tracks=[t.full for t in self.items()],
            last_modified=self.last_modified,
        )

    def items(self) -> list[Track]:
        return self.tracks()

    def tracks(self) -> list[Track]:
        return [Track.from_api(item) for item in self.api.items() if isinstance(item, TidalTrackV1)]

    @property
    def images(self) -> list[MopidyImage] | None:
        return None
