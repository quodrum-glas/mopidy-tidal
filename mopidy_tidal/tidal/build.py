"""Build: tidalapi object → mopidy model.

Pure translation. Each function checks cache, maps fields, stores result.
No intermediate wrapper objects. No session dependency.
"""

from __future__ import annotations

from mopidy.models import Album as MopidyAlbum
from mopidy.models import Artist as MopidyArtist
from mopidy.models import Playlist as MopidyPlaylist
from mopidy.models import Track as MopidyTrack

from mopidy_tidal.display import track_display_name, track_quality
from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.tidal import cache
from mopidy_tidal.uri import URI, URIType


def _year(date_str) -> str | None:
    return date_str[:4] if date_str and len(date_str) >= 4 else None


# -- artists --------------------------------------------------------------


def build_artist(api) -> MopidyArtist:
    cached = cache.get_artist(api.id)
    if cached:
        return cached
    result = MopidyArtist(uri=str(URI(URIType.ARTIST, api.id)), name=api.name)
    cache.put_artist(api.id, result)
    return result


# -- albums ---------------------------------------------------------------


def build_album(api) -> MopidyAlbum:
    cached = cache.get_album(api.id)
    if cached:
        return cached
    result = MopidyAlbum(
        uri=str(URI(URIType.ALBUM, api.id)),
        name=api.name,
        artists=[build_artist(a) for a in (api.artists or [])],
        num_tracks=getattr(api, "num_tracks", 0),
        num_discs=getattr(api, "num_volumes", 1),
        date=_year(getattr(api, "release_date", "")),
    )
    cache.put_album(api.id, result)
    return result


# -- tracks ---------------------------------------------------------------


def build_track(api) -> MopidyTrack:
    cached = cache.get_track(api.id)
    if cached:
        return cached
    result = MopidyTrack(
        uri=str(URI(URIType.TRACK, api.id)),
        name=track_display_name(api),
        track_no=api.track_num,
        disc_no=api.volume_num,
        length=api.duration * 1000,
        artists=[build_artist(a) for a in (api.artists or [])],
        album=build_album(api.album) if api.album else None,
        date=_year(api.album.release_date) if api.album else None,
        genre=track_quality(api),
        comment=track_quality(api),
    )
    cache.put_track(api.id, result)
    return result


def build_tracks(api_tracks) -> list[MopidyTrack]:
    return [build_track(t) for t in api_tracks]


# How many tracks of a list to hydrate up front so the first screen's lookups
# are cache hits; the rest load lazily as the user scrolls.
HYDRATE_WINDOW = 40


def prefetch_tracks(session, track_ids: list[str], window: int = HYDRATE_WINDOW) -> None:
    """Hydrate and cache the first *window* tracks in batched calls.

    Takes *session* explicitly (the pure build_* functions stay session-free).
    Batches of 20 to respect TIDAL's filter[id] cap. Failures are non-fatal —
    a track just stays uncached and is fetched lazily on lookup.
    """
    import logging

    head = track_ids[:window]
    for i in range(0, len(head), 20):
        chunk = head[i : i + 20]
        try:
            build_tracks(session.get_tracks(track_ids=chunk))
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("Prefetch hydrate failed for %r", chunk)


# -- playlists ------------------------------------------------------------


def build_playlist(api, tracks: list[MopidyTrack] | None = None) -> MopidyPlaylist:
    return MopidyPlaylist(
        uri=str(URI(URIType.PLAYLIST, api.id)),
        name=api.name,
        tracks=tracks or [],
        last_modified=to_timestamp(getattr(api, "last_updated", None)),
    )


def build_playlist_as_album(api) -> MopidyAlbum:
    """Wrap a playlist as a MopidyAlbum (for search results — mopidy limitation)."""
    return MopidyAlbum(uri=str(URI(URIType.PLAYLIST, api.id)), name=api.name)
