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

from tidalapi import Session as TidalSession
from tidalapi.models_v1 import (
    Track as TidalTrackV1,
    Album as TidalAlbumV1,
    Artist as TidalArtistV1,
    Playlist as TidalPlaylistV1,
    PageItem as TidalPageItemV1,
    PageLink as TidalPageLinkV1,
    RoleItem as TidalRoleItemV1,
    Mix as TidalMixV1,
    Page as TidalPageV1,
    Video as TidalVideoV1,
)
from tidalapi.models import (
    Album as TidalAlbum,
    Artist as TidalArtist,
    Track as TidalTrack,
    Playlist as TidalPlaylist,
)

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
    TidalTrackV1: Track.from_api,
    TidalVideoV1: return_none,
    TidalAlbumV1: Album.from_api,
    TidalAlbum: Album.from_api,
    TidalArtistV1: Artist.from_api,
    TidalArtist: Artist.from_api,
    TidalPlaylistV1: Playlist.from_api,
    TidalPlaylist: Playlist.from_api,
    TidalMixV1: Mix.from_api,
    TidalPageV1: Page.from_v1,
    TidalPageLinkV1: PageLink.from_v1,
    TidalPageItemV1: PageItem.from_v1,
    TidalRoleItemV1: return_none,
    TidalTrack: Track.from_api,
    list: ItemList.from_v1,
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

def lookup_uri(session: TidalSession, uri: str) -> Model:
    uri = str(uri)
    model_fn = _URI_TYPE_MAP.get(URI.from_string(uri).type)
    if model_fn is None:
        raise ValueError(f"No model for uri: {uri}")
    return model_fn(session, uri=uri)
