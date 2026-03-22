from __future__ import annotations

import mopidy.models as mm
import tidalapi as tdl

from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType

from ._base import Model
from .track import Track


class Mix(Model):
    @classmethod
    def from_api(cls, mix: tdl.Mix) -> Mix:
        uri = URI(URIType.MIX, mix.id)
        return cls(
            ref=mm.Ref.playlist(uri=str(uri), name=f"{mix.title} ({mix.sub_title})"),
            api=mix,
        )

    @classmethod
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Mix:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.MIX:
            raise ValueError(f"Not a valid uri for Mix: {uri}")
        mix = session.mix(parsed.mix)
        return cls(
            ref=mm.Ref.playlist(uri=str(parsed), name=f"{mix.title} ({mix.sub_title})"),
            api=mix,
        )

    @property
    def last_modified(self) -> int:
        return to_timestamp(self.api.updated)

    def build(self) -> mm.Playlist:
        return mm.Playlist(
            uri=self.uri,
            name=self.name,
            tracks=[t.full for t in self.items()],
            last_modified=self.last_modified,
        )

    def items(self) -> list[Track]:
        return self.tracks()

    def tracks(self) -> list[Track]:
        return [
            Track.from_api(item)
            for item in self.api.items()
            if isinstance(item, tdl.Track)
        ]

    @property
    def images(self) -> list[mm.Image] | None:
        return None
