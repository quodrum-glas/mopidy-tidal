from __future__ import annotations

"""Search: query TIDAL, return mopidy SearchResult dicts."""

import logging
from collections import defaultdict
from functools import partial

import tidalapi as tdl
from cachetools import LRUCache, cached
from cachetools.keys import hashkey

from mopidy_tidal.models import model_factory
from mopidy_tidal.models.playlist import PlaylistAsAlbum
from mopidy_tidal.workers import paginated, threaded

logger = logging.getLogger(__name__)

_SEARCH_FIELDS: dict[str, tuple[type, ...]] = {
    "any": (tdl.Album, tdl.Artist, tdl.Track, tdl.Playlist),
    "album": (tdl.Album,),
    "artist": (tdl.Artist,),
    "albumartist": (tdl.Artist,),
    "performer": (tdl.Artist,),
    "composer": (tdl.Artist,),
    "track_name": (tdl.Track,),
}

# TIDAL response key → (mopidy result key, optional wrapper override)
_KEY_MAP: dict[str, tuple[str, object | None]] = {
    "artists": ("artists", None),
    "albums": ("albums", None),
    "tracks": ("tracks", None),
    "playlists": ("albums", PlaylistAsAlbum.from_api),
}

# top_hit type → mopidy result key
_TOP_HIT_KEY: dict[type, str] = {
    tdl.Artist: "artists",
    tdl.Album: "albums",
    tdl.Track: "tracks",
    tdl.Playlist: "albums",
}


@cached(
    LRUCache(maxsize=128),
    key=lambda *args, query, total, exact: hashkey(
        hashkey(**{k: tuple(v) for k, v in query.items()}),
        total,
        exact,
    ),
)
def tidal_search(
    session: tdl.Session,
    /,
    *,
    query: dict[str, list[str]],
    total: int,
    exact: bool = False,
) -> dict[str, list]:
    logger.info("Search query: %r", query)
    query = dict(query)  # don't mutate caller's dict
    queries: dict[tuple[type, ...], list[str]] = {
        _SEARCH_FIELDS[k]: query.pop(k)
        for k in reversed(_SEARCH_FIELDS)
        if k in query
    }
    if query:
        queries[(tdl.Playlist,)] = next(v for v in query.values())

    results: dict[str, list] = defaultdict(list)

    for thread in threaded(*(
        partial(paginated, partial(session.search, q, models=m), total=total)
        for m, q in queries.items()
    )):
        for page in thread:
            top_hit = page.pop("top_hit", None)
            if top_hit:
                key = _TOP_HIT_KEY.get(type(top_hit))
                if key:
                    results[key].append(model_factory(top_hit))

            for k, items in page.items():
                match = _KEY_MAP.get(k)
                if match:
                    out_key, override = match
                    wrap = override or model_factory
                    results[out_key].extend(wrap(i) for i in items)

    logger.info("Search results: %r", {k: len(v) for k, v in results.items()})
    return {k: [i.full for i in v] for k, v in results.items()}
