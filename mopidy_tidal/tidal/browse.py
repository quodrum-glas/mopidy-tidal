"""Browse: URI → list[Ref].

Session-aware navigation. Each function fetches children and returns refs.
Pages, mixes, futures are first-class browsing concepts.
"""

from __future__ import annotations

import logging

from mopidy.models import Ref
from tidalapi.models_v1 import Page as V1Page

from mopidy_tidal.display import feat_item
from mopidy_tidal.tidal import cache
from mopidy_tidal.tidal.build import HYDRATE_WINDOW, build_track, build_tracks, prefetch_tracks
from mopidy_tidal.tidal.refs import album_ref, playlist_ref, refs_for, track_ref
from mopidy_tidal.uri import URI, URIType

logger = logging.getLogger(__name__)


# -- top-level directory --------------------------------------------------

_SECTIONS = (
    "home",
    "explore",
    "for_you",
    "hires",
    "genres",
    "moods",
    "mixes",
    "my_artists",
    "my_albums",
    "my_playlists",
    "my_tracks",
)


def browse_root() -> list[Ref]:
    return [Ref.directory(uri=str(URI(name)), name=name.replace("_", " ").title()) for name in _SECTIONS]


# -- entity browsing ------------------------------------------------------


def browse_artist(session, artist_id: str) -> list[Ref]:
    aid = int(artist_id)
    artist = session.artist(aid)
    result: list[Ref] = []

    # Deferred page
    _store_future(
        lambda: session.get_artist_page(aid),
        key=f"artist-page:{aid}",
        ref_type=Ref.DIRECTORY,
        title=f"Page: {artist.name}",
        result=result,
    )

    # Similar artists (deferred)
    _store_future(
        lambda: artist.similar_artists,
        key=f"artist-similar:{aid}",
        ref_type=Ref.DIRECTORY,
        title=f"Similar: {artist.name}",
        result=result,
    )

    # Radio playlists
    for p in artist.radio:
        ref = playlist_ref(p)
        result.append(ref.replace(name=f"Radio: {ref.name}"))

    # Top tracks
    for t in session.get_artist_tracks(aid):
        result.append(track_ref(t))

    # Albums
    for a in session.get_artist_albums(aid):
        result.append(album_ref(a))

    return result


def browse_album(session, album_id: str) -> list[Ref]:
    aid = int(album_id)
    album = session.album(aid)
    result: list[Ref] = []

    # Deferred page
    _store_future(
        lambda: session.get_album_page(aid),
        key=f"album-page:{aid}",
        ref_type=Ref.DIRECTORY,
        title=f"Page: {album.name}",
        result=result,
    )

    # Artist links (deferred pages)
    for a in album.artists:
        _store_future(
            lambda a_id=int(a.id): session.get_artist_page(a_id),
            key=f"artist-page:{int(a.id)}",
            ref_type=Ref.DIRECTORY,
            title=f"Artist: {a.name}",
            result=result,
        )

    # Similar albums (deferred)
    _store_future(
        lambda: album.similar_albums,
        key=f"album-similar:{aid}",
        ref_type=Ref.DIRECTORY,
        title=f"Similar: {album.name}",
        result=result,
    )

    # Tracks: ref all, warm the per-track cache for the first window only.
    for i, t in enumerate(session.get_album_tracks(aid)):
        if i < HYDRATE_WINDOW:
            build_track(t)
        result.append(track_ref(t))

    return result


def browse_playlist(session, playlist_id: str) -> list[Ref]:
    # Items-only: fast, returns every track's name without hydrating the whole
    # list. Then hydrate just the first window so the first screen's lookups
    # are cache hits; the rest load lazily as the user scrolls.
    tracks = session.get_playlist(playlist_id).tracks
    prefetch_tracks(session, [str(t.id) for t in tracks])
    return [track_ref(t) for t in tracks]


def browse_mix(session, mix_id: str) -> list[Ref]:
    mix = session.mix(mix_id)
    tracks = [t for t in mix.items() if hasattr(t, "track_num")]
    # Mix items come hydrated in one fetch, so warm the first window from them
    # directly (no extra calls); deeper rows resolve lazily.
    build_tracks(tracks[:HYDRATE_WINDOW])
    return [track_ref(t) for t in tracks]


# -- pages (v1 first-class concept) --------------------------------------


def browse_page(session, page_path: str) -> list[Ref]:
    page = session.page.get(page_path)
    return _page_to_refs(page)


def _page_to_refs(page) -> list[Ref]:
    """Convert a Page's items into a flat list of refs via the shared dispatch."""
    return refs_for(page)


# -- futures (deferred content) -------------------------------------------


def browse_future(session, future_uri: str) -> list[Ref]:
    thunk = cache.get_future(future_uri)
    if not thunk:
        return []
    result = thunk()
    # Result could be a Page, a list, or a single item
    if isinstance(result, V1Page):
        return _page_to_refs(result)
    if isinstance(result, list):
        return refs_for(result)
    return refs_for([result]) if result else []


def _store_future(thunk, *, key: str, ref_type: str, title: str, result: list[Ref]) -> None:
    """Create a future ref, store the thunk in cache, append to result.

    *key* is a stable, content-derived identifier (e.g. ``artist-page:42``).
    The resulting future URI is therefore reproducible across browse calls and
    process restarts, unlike one derived from ``hash()`` of the closure.
    """
    uri = str(URI(URIType.FUTURE, key))
    cache.put_future(uri, thunk)
    result.append(Ref(type=ref_type, uri=uri, name=feat_item(title)))


# -- summary sections (user collections, home, explore, etc.) -------------

_SUMMARY_MAP = {
    "home": lambda s: s.home(),
    "explore": lambda s: s.explore(),
    "for_you": lambda s: s.for_you(),
    "hires": lambda s: s.hires_page(),
    "genres": lambda s: s.genres(),
    "moods": lambda s: s.moods(),
    "mixes": lambda s: s.mixes(),
    "my_artists": lambda s: s.get_user_artists(),
    "my_albums": lambda s: s.get_user_albums(),
    "my_playlists": lambda s: s.get_user_playlists(),
    "my_tracks": lambda s: s.get_user_tracks(),
}


def browse_summary(session, name: str) -> list[Ref]:
    fn = _SUMMARY_MAP.get(name)
    if not fn:
        return []
    return refs_for(fn(session))


# -- dispatcher -----------------------------------------------------------


def browse(session, uri: str) -> list[Ref]:
    """Main entry point: parse URI and dispatch to the appropriate browse function."""
    parsed = URI.from_string(uri)

    if parsed.type == URIType.DIRECTORY:
        return browse_root()

    summary_fn = _SUMMARY_MAP.get(parsed.type if isinstance(parsed.type, str) else None)
    if summary_fn:
        return refs_for(summary_fn(session))

    if parsed.type == URIType.ARTIST:
        return browse_artist(session, parsed.artist)
    if parsed.type == URIType.ALBUM:
        return browse_album(session, parsed.album)
    if parsed.type == URIType.PLAYLIST:
        return browse_playlist(session, parsed.playlist)
    if parsed.type == URIType.MIX:
        return browse_mix(session, parsed.mix)
    if parsed.type == URIType.PAGE:
        return browse_page(session, parsed.page)
    if parsed.type == URIType.FUTURE:
        return browse_future(session, str(parsed))

    logger.warning("Unknown browse URI type: %s", parsed.type)
    return []
