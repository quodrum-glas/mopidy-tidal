"""Images: URI → list[MopidyImage].

Fetches the api object and extracts artwork URLs.
No caching — called infrequently, images may change.
"""

from __future__ import annotations

import logging

from mopidy.models import Image

from mopidy_tidal.uri import URI, URIType

logger = logging.getLogger(__name__)

IMAGE_SIZE = 320


def get_images(session, uri: str) -> list[Image]:
    """Resolve images for any tidal URI."""
    parsed = URI.from_string(uri)

    if parsed.type == URIType.TRACK:
        return _track_images(session, parsed.track)
    if parsed.type == URIType.ALBUM:
        return _album_images(session, parsed.album)
    if parsed.type == URIType.ARTIST:
        return _artist_images(session, parsed.artist)
    if parsed.type == URIType.PLAYLIST:
        return _playlist_images(session, parsed.playlist)
    return []


def _track_images(session, track_id: str) -> list[Image]:
    track = session.track(track_id)
    images: list[Image] = []
    if track.album:
        images.extend(_cover(track.album))
    for a in track.artists or []:
        images.extend(_profile(a))
    return images


def _album_images(session, album_id: str) -> list[Image]:
    return _cover(session.album(album_id))


def _artist_images(session, artist_id: str) -> list[Image]:
    return _profile(session.artist(artist_id))


def _playlist_images(session, playlist_id: str) -> list[Image]:
    return _cover(session.playlist(playlist_id))


def _cover(obj) -> list[Image]:
    url = obj.cover(IMAGE_SIZE) if hasattr(obj, "cover") else ""
    return [Image(uri=url, width=IMAGE_SIZE, height=IMAGE_SIZE)] if url else []


def _profile(obj) -> list[Image]:
    url = obj.profile(IMAGE_SIZE) if hasattr(obj, "profile") else ""
    return [Image(uri=url, width=IMAGE_SIZE, height=IMAGE_SIZE)] if url else []
