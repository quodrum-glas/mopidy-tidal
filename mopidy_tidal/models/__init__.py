from __future__ import annotations

"""Model layer: wraps tidalapi objects into mopidy Refs and models."""

__all__ = (
    "Model",
    "Track",
    "Album",
    "Artist",
    "Playlist",
    "PlaylistAsAlbum",
    "Mix",
    "Page",
    "lookup_uri",
    "model_factory",
    "model_factory_map",
)

import logging
from collections.abc import Iterator

import tidalapi as tdl
from tidalapi.models.page import PageItem as TdlPageItem, PageLink as TdlPageLink, RoleItem as TdlRoleItem

from mopidy_tidal.helpers import return_none
from mopidy_tidal.uri import URI, URIType

from ._base import Model
from .album import Album
from .artist import Artist
from .containers import Future, ItemList
from .mix import Mix
from .page import Page, PageItem, PageLink
from .playlist import Playlist, PlaylistAsAlbum
from .track import Track

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------

_MODEL_MAP: dict[type, object] = {
    tdl.Track: Track.from_api,
    tdl.Video: return_none,
    tdl.Album: Album.from_api,
    tdl.Artist: Artist.from_api,
    tdl.Playlist: Playlist.from_api,
    tdl.Mix: Mix.from_api,
    tdl.Page: Page.from_api,
    TdlPageLink: PageLink.from_api,
    TdlPageItem: PageItem.from_api,
    TdlRoleItem: return_none,
    list: ItemList.from_api,
}

_URI_TYPE_MAP: dict[URIType, object] = {
    URIType.TRACK: Track.from_uri,
    URIType.ALBUM: Album.from_uri,
    URIType.ARTIST: Artist.from_uri,
    URIType.PLAYLIST: Playlist.from_uri,
    URIType.MIX: Mix.from_uri,
    URIType.PAGE: Page.from_uri,
    URIType.FUTURE: Future.from_uri,
}


def model_factory(api_item: object) -> Model:
    for cls, factory in _MODEL_MAP.items():
        if isinstance(api_item, cls):
            return factory(api_item)
    raise ValueError(f"No model for: {type(api_item).__name__} {api_item!r}")


def model_factory_map(iterable: object) -> Iterator[Model]:
    for item in iterable:
        try:
            model = model_factory(item)
            if model:
                yield model
        except ValueError as e:
            logger.error(e)


def lookup_uri(session: tdl.Session, uri: str) -> Model:
    uri = str(uri)
    model_fn = _URI_TYPE_MAP.get(URI.from_string(uri).type)
    if model_fn is None:
        raise ValueError(f"No model for uri: {uri}")
    return model_fn(session, uri=uri)
