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

    search_keys = set(query.keys())
    search_term = " ".join(i for l in query.values() for i in l)
    if not search_term:
        return {}

    # Determine which result types to return based on query fields
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

    if len(include) > 1:
        results = session.search(search_term, include=include)
    else:
        results = None

    out: dict[str, list] = defaultdict(list)

    if want_tracks:
        # Hydrate tracks with artists+albums
        raw_tracks = results.tracks[:total] if results else session.search_tracks(search_term, limit=total)
        if raw_tracks:
            max_hydrate = 20
            for i in range(0, len(raw_tracks), max_hydrate):
                hydrated = session.get_tracks(track_ids=[t.id for t in raw_tracks[i:i + max_hydrate]])
                for t in hydrated:
                    try:
                        out["tracks"].append(model_factory(t))
                    except ValueError:
                        pass

    if want_albums:
        albums = results.albums[:total] if results else session.search_albums(search_term, limit=total)
        for a in albums:
            try:
                out["albums"].append(model_factory(a))
            except ValueError:
                pass

    if want_artists:
        artists = results.artists[:total] if results else session.search_artists(search_term, limit=total)
        for a in artists:
            try:
                out["artists"].append(model_factory(a))
            except ValueError:
                pass

    if want_playlists:
        playlists = results.playlists[:total] if results else session.search_playlists(search_term, limit=total)
        for p in playlists:
            try:
                out["albums"].append(PlaylistAsAlbum.from_api(p))
            except (ValueError, AttributeError):
                pass

    logger.info("Search results: %s", {k: len(v) for k, v in out.items()})
    return {k: [i.full for i in v] for k, v in out.items()}
