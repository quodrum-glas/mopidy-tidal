"""Ref construction: tidalapi object → MopidyRef.

Each function is 2-3 lines. No intermediate objects, no caching needed.
"""

from __future__ import annotations

import logging

from mopidy.models import Ref
from tidalapi.models import Album as OapiAlbum
from tidalapi.models import Artist as OapiArtist
from tidalapi.models import Playlist as OapiPlaylist
from tidalapi.models import Track as OapiTrack
from tidalapi.models import Video as OapiVideo
from tidalapi.models_v1 import Album as V1Album
from tidalapi.models_v1 import Artist as V1Artist
from tidalapi.models_v1 import Mix as V1Mix
from tidalapi.models_v1 import Page as V1Page
from tidalapi.models_v1 import PageItem as V1PageItem
from tidalapi.models_v1 import PageLink as V1PageLink
from tidalapi.models_v1 import Playlist as V1Playlist
from tidalapi.models_v1 import Track as V1Track
from tidalapi.models_v1 import Video as V1Video

from mopidy_tidal.display import feat_item
from mopidy_tidal.uri import URI, URIType

logger = logging.getLogger(__name__)


def track_ref(obj) -> Ref:
    return Ref.track(uri=str(URI(URIType.TRACK, obj.id)), name=obj.name)


def album_ref(obj) -> Ref:
    return Ref.album(uri=str(URI(URIType.ALBUM, obj.id)), name=obj.name)


def artist_ref(obj) -> Ref:
    return Ref.artist(uri=str(URI(URIType.ARTIST, obj.id)), name=obj.name)


def playlist_ref(obj) -> Ref:
    return Ref.playlist(uri=str(URI(URIType.PLAYLIST, obj.id)), name=obj.name)


def mix_ref(obj) -> Ref:
    name = f"{obj.title} ({obj.sub_title})" if obj.sub_title else obj.title
    return Ref.playlist(uri=str(URI(URIType.MIX, obj.id)), name=name)


def page_ref(obj) -> Ref:
    return Ref.directory(uri=str(URI(URIType.PAGE)), name=obj.title)


def page_link_ref(obj) -> Ref:
    return Ref.directory(uri=str(URI(URIType.PAGE, obj.api_path)), name=obj.title)


def page_item_ref(obj) -> Ref | None:
    """Convert a PageItem to a Ref based on its declared type."""
    _TYPE_MAP = {
        "TRACK": (URIType.TRACK, Ref.TRACK),
        "ALBUM": (URIType.ALBUM, Ref.ALBUM),
        "ARTIST": (URIType.ARTIST, Ref.ARTIST),
        "PLAYLIST": (URIType.PLAYLIST, Ref.PLAYLIST),
        "MIX": (URIType.MIX, Ref.PLAYLIST),
        "PAGE": (URIType.PAGE, Ref.DIRECTORY),
    }
    entry = _TYPE_MAP.get(obj.type.upper() if obj.type else "")
    if not entry:
        logger.debug("Unknown PageItem type: %s", obj.type)
        return None
    uri_type, ref_type = entry
    uri = URI(uri_type, obj.artifact_id)
    return Ref(type=ref_type, uri=str(uri), name=feat_item(obj.header))


# -- dispatcher -----------------------------------------------------------

_DISPATCH: list[tuple[type, object]] = [
    (V1Track, track_ref),
    (OapiTrack, track_ref),
    (V1Album, album_ref),
    (OapiAlbum, album_ref),
    (V1Artist, artist_ref),
    (OapiArtist, artist_ref),
    (V1Playlist, playlist_ref),
    (OapiPlaylist, playlist_ref),
    (V1Mix, mix_ref),
    (V1Page, page_ref),
    (V1PageLink, page_link_ref),
    (V1PageItem, page_item_ref),
    (V1Video, lambda _: None),
    (OapiVideo, lambda _: None),
]


def ref_for(api_obj) -> Ref | None:
    """Dispatch any tidalapi object to the appropriate ref constructor."""
    for cls, fn in _DISPATCH:
        if isinstance(api_obj, cls):
            return fn(api_obj)
    raise ValueError(f"No ref mapping for: {type(api_obj).__name__}")


def refs_for(iterable) -> list[Ref]:
    """Convert an iterable of tidalapi objects to refs, skipping None/unknown."""
    result = []
    for obj in iterable:
        try:
            ref = ref_for(obj)
            if ref:
                result.append(ref)
        except ValueError:
            logger.debug("Skipping unknown object: %s", type(obj).__name__)
    return result
