from __future__ import annotations

from mopidy.models import Playlist as MopidyPlaylist
from mopidy.models import Ref as MopidyRef
from tidalapi import Session as TidalSession

from mopidy_tidal.cache import cache_future, cached_future
from mopidy_tidal.display import feat_item
from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType

from ._base import Model


class ItemList(Model):
    @classmethod
    def from_v1(cls, items: list) -> ItemList:
        return cls(ref=MopidyRef.playlist(uri=str(URI(URIType.PLAYLIST)), name=None), api=items)

    def items(self) -> list[Model]:
        from . import model_factory_map

        return list(model_factory_map(self.api))

    def tracks(self) -> list[Model]:
        return self.items()

    def build(self) -> MopidyPlaylist:
        return MopidyPlaylist(
            uri=self.uri, name=self.name, tracks=[t.full for t in self.items()], last_modified=to_timestamp("today")
        )


class Future(Model):
    @classmethod
    @cache_future
    def from_v1(cls, future: object, /, *, ref_type: str, title: str) -> Future:
        uri = URI(URIType.FUTURE, str(hash(future)))
        return cls(ref=MopidyRef(type=ref_type, uri=str(uri), name=feat_item(title)), api=future)

    @classmethod
    @cached_future
    def from_cache(cls, session: TidalSession, /, *, uri: str) -> Future | None:
        return None

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Model | None:
        from . import model_factory

        future = cls.from_cache(session, uri=uri)
        if future:
            return model_factory(future.api())
        return None
