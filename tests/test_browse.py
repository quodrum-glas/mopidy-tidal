from __future__ import annotations

"""Browse behaviour tests.

The translation layer is a redesign of the old models/ wrapper, but it must
preserve observable behaviour — most importantly the *number* of API calls it
makes. These tests lock the call counts so an eager rebuild can't silently
start re-fetching the same entity.
"""

from unittest.mock import MagicMock

import pytest

from mopidy_tidal.tidal import cache
from mopidy_tidal.tidal.browse import browse_album, browse_artist


@pytest.fixture(autouse=True)
def _clear_caches():
    cache.clear()
    yield
    cache.clear()


class TestBrowseArtistCallCounts:
    def test_artist_fetched_exactly_once(self):
        session = MagicMock()
        artist = MagicMock()
        artist.name = "Radiohead"
        artist.similar_artists = []
        artist.radio = []
        session.artist.return_value = artist
        session.get_artist_tracks.return_value = []
        session.get_artist_albums.return_value = []

        browse_artist(session, "42")

        # The whole browse resolves the artist a single time and reuses it for
        # both future titles and the radio list (old models/ behaviour).
        assert session.artist.call_count == 1
        assert session.get_artist_tracks.call_count == 1
        assert session.get_artist_albums.call_count == 1

    def test_similar_artists_future_does_not_refetch_artist(self):
        session = MagicMock()
        artist = MagicMock()
        artist.name = "Radiohead"
        artist.similar_artists = []
        artist.radio = []
        session.artist.return_value = artist
        session.get_artist_tracks.return_value = []
        session.get_artist_albums.return_value = []

        refs = browse_artist(session, "42")

        # Resolve the "Similar" future and confirm it reads the already-fetched
        # artist object rather than calling session.artist again.
        similar = next(r for r in refs if r.uri == "tidal:future:artist-similar:42")
        thunk = cache.get_future(similar.uri)
        thunk()
        assert session.artist.call_count == 1


class TestBrowseAlbumCallCounts:
    def test_album_fetched_exactly_once(self):
        session = MagicMock()
        album = MagicMock()
        album.name = "OK Computer"
        album.artists = []
        album.similar_albums = []
        session.album.return_value = album
        session.get_album_tracks.return_value = []

        browse_album(session, "55")

        assert session.album.call_count == 1
        assert session.get_album_tracks.call_count == 1


class TestBrowseDefersSubNavigation:
    """A browse must fetch only what *this* screen shows. Sub-navigations
    (an entity's page, its similar list) are futures and must not be fetched —
    or even read — until the user browses into them.
    """

    def test_artist_page_and_similar_not_fetched_during_browse(self):
        session = MagicMock()
        artist = MagicMock()
        artist.name = "Radiohead"
        artist.radio = []
        # similar_artists must not be read while merely listing the artist.
        type(artist).similar_artists = property(
            lambda self: pytest.fail("similar_artists accessed eagerly during browse")
        )
        session.artist.return_value = artist
        session.get_artist_tracks.return_value = []
        session.get_artist_albums.return_value = []

        browse_artist(session, "42")

        assert session.get_artist_page.call_count == 0

    def test_album_page_and_similar_not_fetched_during_browse(self):
        session = MagicMock()
        album = MagicMock()
        album.name = "OK Computer"
        album.artists = []
        type(album).similar_albums = property(lambda self: pytest.fail("similar_albums accessed eagerly during browse"))
        session.album.return_value = album
        session.get_album_tracks.return_value = []

        browse_album(session, "55")

        assert session.get_album_page.call_count == 0

    def test_artist_page_fetched_only_when_future_resolved(self):
        session = MagicMock()
        artist = MagicMock()
        artist.name = "Radiohead"
        artist.similar_artists = []
        artist.radio = []
        session.artist.return_value = artist
        session.get_artist_tracks.return_value = []
        session.get_artist_albums.return_value = []
        session.get_artist_page.return_value = []

        refs = browse_artist(session, "42")
        assert session.get_artist_page.call_count == 0

        page_ref = next(r for r in refs if r.uri == "tidal:future:artist-page:42")
        cache.get_future(page_ref.uri)()
        assert session.get_artist_page.call_count == 1


class TestBrowseWarmsTrackCache:
    """Browsing a track list warms the per-track cache so Mopidy's follow-up
    per-track lookup() calls (which the actor serialises) are cache hits
    instead of N serial session.track() round trips.
    """

    def test_browse_playlist_caches_tracks(self):
        from mopidy_tidal.tidal.browse import browse_playlist
        from tests.test_models import _fake_track

        session = MagicMock()
        session.get_playlist_tracks.return_value = [_fake_track("1", "A"), _fake_track("2", "B")]

        browse_playlist(session, "pl1")

        # Both tracks are now in the cache, ready for lookup() without a fetch.
        assert cache.get_track("1") is not None
        assert cache.get_track("2") is not None
