from __future__ import annotations

"""Search: query TIDAL via oapi, return mopidy SearchResult dicts."""

import logging
from collections import defaultdict

from cachetools import LRUCache, cached
from cachetools.keys import hashkey

from mopidy_tidal.models import model_factory
from mopidy_tidal.models.playlist import PlaylistAsAlbum

logger = logging.getLogger(__name__)


@cached(
    LRUCache(maxsize=128),
    key=lambda *args, query, total, exact: hashkey(
        hashkey(**{k: tuple(v) for k, v in query.items()}),
        total,
        exact,
    ),
)
def tidal_search(session, /, *, query, total, exact=False):
    logger.info("Search query: %r (total=%d, exact=%s)", query, total, exact)

    parts = []
    for field in ("any", "track_name", "album", "artist", "albumartist", "performer", "composer"):
        if field in query:
            parts.extend(query[field])
    search_term = " ".join(parts)
    if not search_term:
        return {}

    # Determine which result types to return based on query fields
    want_tracks = "any" in query or "track_name" in query
    want_albums = "any" in query or "album" in query
    want_artists = "any" in query or any(
        f in query for f in ("artist", "albumartist", "performer", "composer")
    )
    want_playlists = "any" in query

    results = session.search(search_term)
    out: dict[str, list] = defaultdict(list)

    if want_tracks:
        # Hydrate tracks with artists+albums
        raw_tracks = results.tracks[:total]
        if raw_tracks:
            hydrated = session.get_tracks(track_ids=[t.id for t in raw_tracks])
            for t in hydrated:
                try:
                    out["tracks"].append(model_factory(t))
                except ValueError:
                    pass

    if want_albums:
        for a in results.albums[:total]:
            try:
                out["albums"].append(model_factory(a))
            except ValueError:
                pass

    if want_artists:
        for a in results.artists[:total]:
            try:
                out["artists"].append(model_factory(a))
            except ValueError:
                pass

    if want_playlists:
        for p in results.playlists[:total]:
            try:
                out["albums"].append(PlaylistAsAlbum.from_api(p))
            except (ValueError, AttributeError):
                pass

    logger.info("Search results: %s", {k: len(v) for k, v in out.items()})
    return {k: [i.full for i in v] for k, v in out.items()}
