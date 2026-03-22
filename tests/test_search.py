from __future__ import annotations

from unittest.mock import MagicMock, patch

import tidalapi as tdl

from mopidy_tidal.search import _KEY_MAP, _SEARCH_FIELDS, _TOP_HIT_KEY, tidal_search


class TestSearchFields:
    def test_any_includes_all_types(self):
        assert tdl.Track in _SEARCH_FIELDS["any"]
        assert tdl.Album in _SEARCH_FIELDS["any"]
        assert tdl.Artist in _SEARCH_FIELDS["any"]
        assert tdl.Playlist in _SEARCH_FIELDS["any"]

    def test_track_name_maps_to_track(self):
        assert _SEARCH_FIELDS["track_name"] == (tdl.Track,)


class TestKeyMap:
    def test_playlists_map_to_albums(self):
        key, override = _KEY_MAP["playlists"]
        assert key == "albums"
        assert override is not None

    def test_tracks_no_override(self):
        key, override = _KEY_MAP["tracks"]
        assert key == "tracks"
        assert override is None


class TestTopHitKey:
    def test_playlist_maps_to_albums(self):
        assert _TOP_HIT_KEY[tdl.Playlist] == "albums"

    def test_track_maps_to_tracks(self):
        assert _TOP_HIT_KEY[tdl.Track] == "tracks"


class TestTidalSearch:
    def _mock_session(self, search_results):
        session = MagicMock(spec=tdl.Session)
        session.search.return_value = search_results
        return session

    def test_basic_track_search(self):
        from tests.test_models import _fake_track

        track = _fake_track("1", "Song")
        session = self._mock_session({"tracks": [track], "top_hit": None})

        result = tidal_search(
            session,
            query={"track_name": ["Song unique test"]},
            total=10,
            exact=False,
        )
        assert "tracks" in result
        assert len(result["tracks"]) >= 1

    def test_empty_results(self):
        session = self._mock_session({"tracks": [], "albums": [], "artists": []})
        result = tidal_search(
            session,
            query={"any": ["nonexistent query xyz"]},
            total=10,
            exact=False,
        )
        assert all(v == [] for v in result.values())
