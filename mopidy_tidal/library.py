from __future__ import annotations

"""Library provider: browse, search, lookup, images."""

import logging

from mopidy import backend
from mopidy.models import Ref, SearchResult
from tidalapi.exceptions import NotFoundError, TidalError

from mopidy_tidal.display import tidal_item
from mopidy_tidal.helpers import login_required
from mopidy_tidal.models import lookup_uri, model_factory_map
from mopidy_tidal.search import tidal_search
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

        # Use enhanced oapi user collection methods
        if field in _ARTIST_FIELDS:
            artists = session.get_user_artists()
            return [tidal_item(a.name) for a in artists]
        if field == "album":
            albums = session.get_user_albums()
            return [tidal_item(a.name) for a in albums]
        if field == "track":
            tracks = session.get_user_tracks()
            return [tidal_item(t.name) for t in tracks]
        
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

    @login_required(
        lambda b: [Ref.directory(uri="tidal:directory", name=f"Visit {b._login_url} to log in")]
    )
    def browse(self, uri: str) -> list[Ref]:
        logger.debug("TidalLibraryProvider.browse %s", uri)
        try:
            parsed = URI.from_string(uri)
        except ValueError:
            return []

        session = self.backend.session

        summaries = {
            "home": session.home,
            "explore": session.explore,
            "for_you": session.for_you,
            "hires": session.hires_page,
            "genres": session.genres,
            "moods": session.moods,
            "mixes": session.mixes,
            "my_artists": session.get_user_artists,
            "my_albums": session.get_user_albums,
            "my_playlists": session.get_user_playlists,
            "my_tracks": session.get_user_tracks,
        }

        if parsed.type == URIType.DIRECTORY:
            return [
                Ref.directory(uri=str(URI(name)), name=name.replace("_", " ").title())
                for name in summaries
            ]

        summary = summaries.get(parsed.type)
        if summary:
            return [m.ref for m in model_factory_map(summary())]

        try:
            model = lookup_uri(session, uri)
        except (ValueError, NotFoundError, TidalError):
            logger.warning("Browse request failed for: %s", uri)
            return []
        return [item.ref for item in model.items()]

    @login_required(SearchResult())
    def search(
        self,
        query: dict | None = None,
        uris: list[str] | None = None,
        exact: bool = False,
    ) -> SearchResult:
        total = self.backend.pagination_max_results
        return SearchResult(**tidal_search(
            self.backend.session, query=query, total=total, exact=exact,
        ))

    def get_images(self, uris: list[str]) -> dict[str, list]:
        result: dict[str, list] = {}
        for uri in uris:
            try:
                result[uri] = lookup_uri(self.backend.session, uri).images
            except (ValueError, NotFoundError, TidalError):
                result[uri] = []
        return result

    def lookup(self, uris: str | list[str]) -> list:
        logger.debug("TidalLibraryProvider.lookup(%r)", uris)
        if isinstance(uris, str):
            uris = [uris]
        tracks = []
        for uri in uris:
            try:
                tracks.extend(
                    t.full for t in lookup_uri(self.backend.session, uri).tracks()
                )
            except (ValueError, NotFoundError, TidalError):
                logger.warning("Lookup failed for: %s", uri)
        return tracks
