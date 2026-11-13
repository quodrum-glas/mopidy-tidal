"""tidal/ — lean translation layer between tidalapi and mopidy.

Modules:
    refs    — tidalapi obj → MopidyRef
    build   — tidalapi obj → MopidyTrack/Album/Artist/Playlist
    browse  — URI → list[Ref] (navigation)
    images  — URI → list[MopidyImage]
    cache   — shared LRU/TTL caches
"""

from mopidy_tidal.tidal.browse import browse  # noqa: F401
from mopidy_tidal.tidal.build import (  # noqa: F401
    build_album,
    build_artist,
    build_playlist,
    build_playlist_as_album,
    build_track,
    build_tracks,
)
from mopidy_tidal.tidal.images import get_images, get_images_batch  # noqa: F401
from mopidy_tidal.tidal.refs import ref_for, refs_for  # noqa: F401

__all__ = [
    "browse",
    "build_album",
    "build_artist",
    "build_playlist",
    "build_playlist_as_album",
    "build_track",
    "build_tracks",
    "get_images",
    "get_images_batch",
    "ref_for",
    "refs_for",
]
