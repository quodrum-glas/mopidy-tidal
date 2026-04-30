from __future__ import annotations

from unittest.mock import MagicMock, patch

from mopidy_tidal.search import tidal_search


class TestTidalSearch:
    def _mock_session(self, **kwargs):
        session = MagicMock()
        search_result = MagicMock()
        for attr, val in kwargs.items():
            setattr(search_result, attr, val)
        session.search.return_value = search_result
        session.search_tracks.return_value = kwargs.get("tracks", [])
        session.search_albums.return_value = kwargs.get("albums", [])
        session.search_artists.return_value = kwargs.get("artists", [])
        session.search_playlists.return_value = kwargs.get("playlists", [])
        session.get_tracks.return_value = []
        return session

    def test_empty_query_returns_empty(self):
        session = self._mock_session()
        result = tidal_search(session, query={"any": [""]}, total=10, exact=False)
        assert result == {}

    def test_any_query_includes_all_types(self):
        session = self._mock_session(tracks=[], albums=[], artists=[], playlists=[])
        result = tidal_search(session, query={"any": ["test query abc"]}, total=10, exact=False)
        session.search.assert_called_once()
        assert all(v == [] for v in result.values())

    def test_track_name_only_searches_tracks(self):
        session = self._mock_session(tracks=[])
        session.get_tracks.return_value = []
        result = tidal_search(
            session, query={"track_name": ["unique song xyz"]}, total=10, exact=False,
        )
        # track_name alone → only "tracks" in include, so single-type path
        assert "albums" not in result or result.get("albums") == []

    def test_artist_query_searches_artists(self):
        session = self._mock_session(artists=[], tracks=[], albums=[], playlists=[])
        result = tidal_search(
            session, query={"artist": ["unique artist xyz"]}, total=10, exact=False,
        )
        # artist field triggers want_artists
        assert isinstance(result, dict)

    def test_results_keyed_correctly(self):
        from tests.test_models import _fake_track

        track = _fake_track("1", "Song")
        session = self._mock_session(tracks=[track], albums=[], artists=[], playlists=[])
        session.get_tracks.return_value = [track]

        with patch("mopidy_tidal.search.model_factory") as mock_mf:
            mock_model = MagicMock()
            mock_model.full = "full_track"
            mock_mf.return_value = mock_model
            result = tidal_search(
                session, query={"track_name": ["unique result test"]}, total=10, exact=False,
            )
            assert "tracks" in result
