from __future__ import unicode_literals

import logging

from mopidy import backend
from mopidy.models import Ref, SearchResult

import mopidy_tidal.session
from mopidy_tidal.models import lookup_uri, model_factory_map, Track
from mopidy_tidal.search import tidal_search
from mopidy_tidal.display import tidal_item
from mopidy_tidal.uri import URI, URIType

logger = logging.getLogger(__name__)


class TidalLibraryProvider(backend.LibraryProvider):
    root_directory = Ref.directory(uri=str(URI(URIType.DIRECTORY)), name="Tidal")

    def get_distinct(self, field, query=None):
        from mopidy_tidal.search import tidal_search

        logger.info("Browsing distinct %s with query %r", field, query)
        session = self.backend.session

        if not query:  # library root
            if field == "artist" or field == "albumartist":
                return [
                    tidal_item(a.name) for a in session.user.favorites.artists()
                ]
            elif field == "album":
                return [
                    tidal_item(a.name) for a in session.user.favorites.albums()
                ]
            elif field == "track":
                return [
                    tidal_item(t.name) for t in session.user.favorites.tracks()
                ]
        else:
            if field == "artist":
                return [
                    tidal_item(a.name) for a in session.user.favorites.artists()
                ]
            elif field == "album" or field == "albumartist":
                return [
                    tidal_item(album.name)
                    for artist in tidal_search(session, query=query, exact=True)["artists"]
                    for album in artist.albums()
                ]
            elif field == "track":
                return [
                    tidal_item(t.name) for t in session.user.favorites.tracks()
                ]
            pass

        logger.warning("Browse distinct failed for: %s", field)
        return []

    def browse(self, uri: str) -> list[Ref]:
        logger.debug("TidalLibraryProvider.browse %s", uri)
        uri = URI.from_string(uri)
        if not uri:
            return []

        session: mopidy_tidal.session.PersistentSession = self.backend.session

        # summaries

        summaries = {
            "home": session.home,
            "for_you": session.for_you,
            "explore": session.explore,
            "hi_res": session.hires_page,
            "genres": session.genres,
            "local_genres": session.local_genres,
            "moods": session.moods,
            "mixes": session.mixes,
            "my_artists": session.user.favorites.artists,
            "my_albums": session.user.favorites.albums,
            "my_playlists": session.user.favorites.playlists,
            "my_tracks": session.user.favorites.tracks,
            # "my_mixes": session.user.favorites.mixes_and_radio,
            "playlists": session.user.playlists,
        }

        if uri.type == URIType.DIRECTORY:
            return [
                Ref.directory(uri=str(URI(summary)), name=summary.replace("_", " ").title())
                for summary in summaries
            ]

        summary = summaries.get(uri.type)
        if summary:
            return [m.ref for m in model_factory_map(summary())]

        # details

        try:
            model = lookup_uri(session, uri)
        except ValueError:
            logger.warning("Browse request failed to lookup %s", uri)
        else:
            try:
                return [item.ref for item in model]
            except TypeError:
                logger.warning("Browse request failed to iterate %s (%s)", uri, model)

        return []

    def search(self, query=None, uris=None, exact=False):
        total = self.backend.get_config("search_result_count")
        search_result = tidal_search(self.backend.session, query=query, total=total, exact=exact)
        search_result = {
            k: [item.model for item in items]
            for k, items in search_result.items()
        }
        return SearchResult(**search_result)

    def get_images(self, uris):
        images = {
            uri: lookup_uri(self.backend.session, uri).images
            for uri in uris
        }
        return images

    def lookup(self, uri):
        logger.debug("TidalLibraryProvider.lookup(%r)", uri)
        return [
            t.model
            for t in lookup_uri(self.backend.session, uri).tracks
        ]
