from __future__ import annotations

"""Library provider: browse, search, lookup, images."""

import logging

from mopidy import backend
from mopidy.models import Ref, SearchResult
from tidalapi.exceptions import NotFoundError, TidalError

from mopidy_tidal.display import tidal_item
from mopidy_tidal.helpers import login_required
from mopidy_tidal.search import tidal_search
from mopidy_tidal.tidal import browse, build_track, build_tracks, cache, get_images_batch
from mopidy_tidal.uri import URI, URIType

_ARTIST_FIELDS = frozenset({"artist", "albumartist", "performer", "composer"})

logger = logging.getLogger(__name__)


class TidalLibraryProvider(backend.LibraryProvider):
    root_directory = Ref.directory(uri=str(URI(URIType.DIRECTORY)), name="Tidal")

    @login_required([])
    def get_distinct(self, field: str, query: dict | None = None) -> list[str]:
        logger.debug("get_distinct field=%s query=%r", field, query)
        session = self.backend.session

        if query:
            return self._distinct_from_search(field, query)

        if field in _ARTIST_FIELDS:
            return [tidal_item(a.name) for a in session.get_user_artists()]
        if field == "album":
            return [tidal_item(a.name) for a in session.get_user_albums()]
        if field == "track":
            return [tidal_item(t.name) for t in session.get_user_tracks()]
        return []

    def _distinct_from_search(self, field: str, query: dict) -> list[str]:
        results = tidal_search(self.backend.session, query=query, total=50, exact=True)
        if field in _ARTIST_FIELDS:
            return [tidal_item(a.name) for a in results.get("artists", [])]
        if field == "album":
            return [tidal_item(a.name) for a in results.get("albums", [])]
        if field == "track":
            return [tidal_item(t.name) for t in results.get("tracks", [])]
        return []

    @login_required(lambda b: [Ref.directory(uri="tidal:directory", name=f"Visit {b._login_url} to log in")])
    def browse(self, uri: str) -> list[Ref]:
        logger.debug("TidalLibraryProvider.browse %s", uri)
        try:
            return browse(self.backend.session, uri)
        except (ValueError, NotFoundError, TidalError):
            logger.warning("Browse request failed for: %s", uri)
            return []

    @login_required(SearchResult())
    def search(self, query: dict | None = None, uris: list[str] | None = None, exact: bool = False) -> SearchResult:
        total = self.backend.pagination_max_results
        return SearchResult(**tidal_search(self.backend.session, query=query, total=total, exact=exact))

    def get_images(self, uris: list[str]) -> dict[str, list]:
        # Mopidy hands the whole page of URIs to the backend at once, so group
        # them into batched API calls (one get_tracks + one get_albums for all
        # track covers) instead of a request per item. Per-item requests are
        # what triggers TIDAL rate-limiting on a fresh track list.
        if not uris:
            return {}
        return get_images_batch(self.backend.session, uris)

    def lookup(self, uris: str | list[str]) -> list:
        logger.debug("TidalLibraryProvider.lookup(%r)", uris)
        if isinstance(uris, str):
            uris = [uris]
        tracks: list = []
        for uri in uris:
            try:
                tracks.extend(self._lookup_uri(uri))
            except (ValueError, NotFoundError, TidalError):
                logger.warning("Lookup failed for: %s", uri)
        return tracks

    def _lookup_uri(self, uri: str) -> list:
        """Resolve a URI to built MopidyTrack objects."""
        session = self.backend.session
        parsed = URI.from_string(uri)

        if parsed.type == URIType.TRACK:
            # Reuse the already-built track if it was cached by a prior
            # browse/search, skipping the session.track() round trip entirely
            # (tracks are immutable, so this is always safe).
            cached = cache.get_track(parsed.track)
            if cached is not None:
                return [cached]
            return [build_track(session.track(parsed.track))]
        if parsed.type == URIType.ALBUM:
            return build_tracks(session.get_album_tracks(int(parsed.album)))
        if parsed.type == URIType.PLAYLIST:
            return build_tracks(session.get_playlist_tracks(parsed.playlist))
        if parsed.type == URIType.MIX:
            mix = session.mix(parsed.mix)
            return build_tracks(t for t in mix.items() if hasattr(t, "track_num"))
        if parsed.type == URIType.ARTIST:
            return build_tracks(session.get_artist_tracks(int(parsed.artist)))
        return []
