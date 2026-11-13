from __future__ import annotations

"""Search: query TIDAL via oapi, return mopidy SearchResult dicts."""

import logging
from collections import defaultdict

from cachetools import LRUCache, cached
from cachetools.keys import hashkey

from mopidy_tidal.tidal.build import build_album, build_artist, build_playlist_as_album, build_track

logger = logging.getLogger(__name__)

# TIDAL caps each relationship in a searchResults response at 20 items and
# ignores page[limit]. Beyond that, results come from cursor pagination on the
# per-type endpoints, so the single combined request is only worth it when the
# caller wants no more than one page.
_SEARCH_PAGE = 20


@cached(
    LRUCache(maxsize=128),
    key=lambda *args, query, total, exact: hashkey(hashkey(**{k: tuple(v) for k, v in query.items()}), total, exact),
)
def tidal_search(session, /, *, query, total, exact=False):
    logger.info("Search query: %r (total=%d, exact=%s)", query, total, exact)

    search_keys = set(query.keys())
    search_term = " ".join(i for v in query.values() for i in v)
    if not search_term:
        return {}

    want_tracks = search_keys.intersection({"any", "track_name"})
    want_albums = search_keys.intersection({"any", "album"})
    want_artists = search_keys.intersection({"any", "artist", "albumartist", "performer", "composer"})
    want_playlists = search_keys.intersection({"any", "comment", "date", "genre"})

    include = []
    if want_tracks:
        include.append("tracks")
    if want_albums:
        include.append("albums")
    if want_artists:
        include.append("artists")
    if want_playlists:
        include.append("playlists")

    combined = len(include) > 1 and total <= _SEARCH_PAGE
    results = session.search(search_term, include=include) if combined else None

    out: dict[str, list] = defaultdict(list)

    if want_tracks:
        raw_tracks = results.tracks[:total] if results else session.search_tracks(search_term, limit=total)
        if raw_tracks:
            for i in range(0, len(raw_tracks), 20):
                hydrated = session.get_tracks(track_ids=[t.id for t in raw_tracks[i : i + 20]])
                out["tracks"].extend(build_track(t) for t in hydrated)

    if want_albums:
        albums = results.albums[:total] if results else session.search_albums(search_term, limit=total)
        out["albums"].extend(build_album(a) for a in albums)

    if want_artists:
        artists = results.artists[:total] if results else session.search_artists(search_term, limit=total)
        out["artists"].extend(build_artist(a) for a in artists)

    if want_playlists:
        playlists = results.playlists[:total] if results else session.search_playlists(search_term, limit=total)
        for p in playlists:
            try:
                out["albums"].append(build_playlist_as_album(p))
            except (ValueError, AttributeError):
                pass

    logger.info("Search results: %s", {k: len(v) for k, v in out.items()})
    return dict(out)
