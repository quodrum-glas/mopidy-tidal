"""Caching for built mopidy models.

Tracks are immutable → large LRU, no TTL.
Albums/Artists are stable → LRU with generous size.
Collections (playlist membership) are volatile → short TTL.
Futures (deferred page content) → TTL.
"""

from __future__ import annotations

from cachetools import LRUCache, TTLCache

_tracks: LRUCache = LRUCache(maxsize=16_384)
_albums: LRUCache = LRUCache(maxsize=4_096)
_artists: LRUCache = LRUCache(maxsize=4_096)
_collections: TTLCache = TTLCache(maxsize=1_024, ttl=300)
_futures: TTLCache = TTLCache(maxsize=512, ttl=86_400)


# -- tracks (immutable) ---------------------------------------------------


def get_track(track_id):
    return _tracks.get(str(track_id))


def put_track(track_id, mopidy_track):
    _tracks[str(track_id)] = mopidy_track


# -- albums ---------------------------------------------------------------


def get_album(album_id):
    return _albums.get(str(album_id))


def put_album(album_id, mopidy_album):
    _albums[str(album_id)] = mopidy_album


# -- artists --------------------------------------------------------------


def get_artist(artist_id):
    return _artists.get(str(artist_id))


def put_artist(artist_id, mopidy_artist):
    _artists[str(artist_id)] = mopidy_artist


# -- collections (volatile) -----------------------------------------------


def get_collection(key: str):
    return _collections.get(key)


def put_collection(key: str, items: list):
    _collections[key] = items


# -- futures (deferred page content) --------------------------------------


def get_future(uri: str):
    return _futures.get(uri)


def put_future(uri: str, thunk):
    _futures[uri] = thunk


# -- maintenance ----------------------------------------------------------


def clear():
    _tracks.clear()
    _albums.clear()
    _artists.clear()
    _collections.clear()
    _futures.clear()
