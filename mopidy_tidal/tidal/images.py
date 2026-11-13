"""Images: URI → list[MopidyImage].

Resolves artwork URLs for a URI, cached per URI (the old models layer cached
the looked-up model, so repeated image requests for the same URI were free).
"""

from __future__ import annotations

import logging

from mopidy.models import Image

from mopidy_tidal.tidal import cache
from mopidy_tidal.uri import URI, URIType

logger = logging.getLogger(__name__)

IMAGE_SIZE = 320


def get_images(session, uri: str) -> list[Image]:
    """Resolve images for any tidal URI (cached per URI)."""
    cached = cache.get_images(uri)
    if cached is not None:
        return cached

    parsed = URI.from_string(uri)
    if parsed.type == URIType.TRACK:
        images = _track_images(session, parsed.track)
    elif parsed.type == URIType.ALBUM:
        images = _album_images(session, parsed.album)
    elif parsed.type == URIType.ARTIST:
        images = _artist_images(session, parsed.artist)
    elif parsed.type == URIType.PLAYLIST:
        images = _playlist_images(session, parsed.playlist)
    else:
        images = []

    cache.put_images(uri, images)
    return images


def get_images_batch(session, uris: list[str]) -> dict[str, list[Image]]:
    """Resolve images for a whole page of URIs with grouped API calls.

    Mopidy hands the entire page to the backend in one call, so track URIs are
    coalesced into a single ``get_tracks(filter[id]=...)`` plus a single
    ``get_albums(filter[id]=..., include=coverArt)`` — two requests for the
    page instead of one (or more) per track. This is what keeps TIDAL from
    rate-limiting a fresh track list. Non-track URIs and cache hits are handled
    individually (they are already one call each).
    """
    result: dict[str, list[Image]] = {}
    pending_tracks: list[tuple[str, str]] = []  # (uri, track_id)

    for uri in uris:
        cached = cache.get_images(uri)
        if cached is not None:
            result[uri] = cached
            continue
        try:
            parsed = URI.from_string(uri)
        except ValueError:
            result[uri] = []
            continue
        if parsed.type == URIType.TRACK:
            pending_tracks.append((uri, parsed.track))
        else:
            try:
                result[uri] = get_images(session, uri)
            except Exception:  # noqa: BLE001 - one bad URI must not sink the page
                logger.warning("Image lookup failed for %s", uri)
                result[uri] = []

    if pending_tracks:
        result.update(_batch_track_images(session, pending_tracks))
    return result


def _batch_track_images(session, pending: list[tuple[str, str]]) -> dict[str, list[Image]]:
    """Fetch covers for many tracks in two grouped calls.

    1. get_tracks(filter[id]=...) → each track's album id (one call).
    2. get_albums(filter[id]=..., include=coverArt) → every cover (one call).
    """
    out: dict[str, list[Image]] = {uri: [] for uri, _ in pending}
    track_ids = [tid for _, tid in pending]

    try:
        tracks = session.get_tracks(track_ids=track_ids)
    except Exception:  # noqa: BLE001
        logger.warning("Batch track fetch failed for %r", track_ids)
        return out

    # track id -> album id
    album_of: dict[str, str] = {}
    album_ids: list[str] = []
    for t in tracks:
        if t.album:
            aid = str(t.album.id)
            album_of[str(t.id)] = aid
            if aid not in album_ids:
                album_ids.append(aid)

    covers = _batch_album_covers(session, album_ids)

    for uri, tid in pending:
        aid = album_of.get(tid)
        images = covers.get(aid, []) if aid else []
        out[uri] = images
        cache.put_images(uri, images)
    return out


def _batch_album_covers(session, album_ids: list[str]) -> dict[str, list[Image]]:
    """One get_albums(filter[id]=..., include=coverArt) call for all covers."""
    if not album_ids:
        return {}
    try:
        albums = session.get_albums(album_ids=album_ids)
    except Exception:  # noqa: BLE001
        logger.warning("Batch album fetch failed for %r", album_ids)
        return {}
    covers: dict[str, list[Image]] = {}
    for a in albums:
        imgs = _cover(a)
        covers[str(a.id)] = imgs
        cache.put_images(str(URI(URIType.ALBUM, a.id)), imgs)
    return covers


def _track_images(session, track_id: str) -> list[Image]:
    """A track's cover art.

    The album attached to a track from ``session.track()`` is NOT
    cover-hydrated — ``track.album.cover()`` is empty. The cover only exists on
    the album resource fetched with coverArt included, so resolve it via the
    album (cached per album URI so tracks sharing an album share the fetch).
    """
    track = session.track(track_id)
    if not track.album:
        return []
    return _album_images(session, str(track.album.id))


def _album_images(session, album_id: str) -> list[Image]:
    album_uri = str(URI(URIType.ALBUM, album_id))
    cached = cache.get_images(album_uri)
    if cached is not None:
        return cached
    images = _cover(session.album(album_id))
    cache.put_images(album_uri, images)
    return images


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
