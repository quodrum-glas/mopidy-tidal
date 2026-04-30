from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mopidy.models import Ref, SearchResult

from mopidy_tidal.library import TidalLibraryProvider
from mopidy_tidal.playback import TidalPlaybackProvider

# -- Playback -------------------------------------------------------------


@pytest.fixture()
def playback():
    p = TidalPlaybackProvider.__new__(TidalPlaybackProvider)
    p.backend = MagicMock()
    p.backend.quality = "HIGH"
    p._TidalPlaybackProvider__cache = {}  # fresh instance-level cache
    return p


class TestPlaybackTranslateUri:
    def test_bts_manifest(self, playback):
        stream = MagicMock()
        stream.is_drm = False
        stream.is_mpd = False
        stream.is_bts = True
        stream.manifest_mime_type = "application/vnd.tidal.bts"
        stream.audio_quality = "LOSSLESS"
        stream.codec = "FLAC"
        stream.bit_depth = 16
        stream.sample_rate = 44100
        stream.drm_system = ""
        bts = MagicMock()
        bts.get_urls.return_value = ["https://stream.tidal.com/track.flac"]
        stream.bts = bts
        playback.backend.session.get_stream.return_value = stream

        url = playback.translate_uri("tidal:track:123")
        assert url == "https://stream.tidal.com/track.flac"

    def test_bts_no_urls_returns_none(self, playback):
        stream = MagicMock()
        stream.is_drm = False
        stream.is_mpd = False
        stream.is_bts = True
        stream.manifest_mime_type = "application/vnd.tidal.bts"
        stream.audio_quality = "HIGH"
        stream.codec = "AAC"
        stream.bit_depth = 16
        stream.sample_rate = 44100
        stream.drm_system = ""
        bts = MagicMock()
        bts.get_urls.return_value = []
        stream.bts = bts
        playback.backend.session.get_stream.return_value = stream

        assert playback.translate_uri("tidal:track:456") is None

    def test_bts_none_returns_none(self, playback):
        stream = MagicMock()
        stream.is_drm = False
        stream.is_mpd = False
        stream.is_bts = True
        stream.bts = None
        stream.manifest_mime_type = "application/vnd.tidal.bts"
        stream.audio_quality = "HIGH"
        stream.drm_system = ""
        playback.backend.session.get_stream.return_value = stream

        assert playback.translate_uri("tidal:track:457") is None

    def test_unknown_manifest_returns_none(self, playback):
        stream = MagicMock()
        stream.is_drm = False
        stream.is_bts = False
        stream.is_mpd = False
        stream.manifest_mime_type = "application/unknown"
        stream.audio_quality = "HIGH"
        stream.codec = "AAC"
        stream.bit_depth = 16
        stream.sample_rate = 44100
        stream.drm_system = ""
        playback.backend.session.get_stream.return_value = stream

        assert playback.translate_uri("tidal:track:789") is None

    def test_error_returns_none_via_backoff(self, playback):
        playback.backend.session.get_stream.side_effect = RuntimeError("API down")
        assert playback.translate_uri("tidal:track:999") is None


# -- Library --------------------------------------------------------------


@pytest.fixture()
def library():
    p = TidalLibraryProvider.__new__(TidalLibraryProvider)
    p.backend = MagicMock()
    p.backend._config = {"tidal": {"search_result_count": 50}}
    p.backend.EXT = "tidal"
    p.backend.logged_in = True
    p.backend.pagination_max_results = 40
    return p


class TestLibraryBrowse:
    def test_root_returns_directories(self, library):
        refs = library.browse("tidal:directory")
        assert all(r.type == Ref.DIRECTORY for r in refs)
        names = [r.name for r in refs]
        assert "Genres" in names
        assert "My Playlists" in names

    def test_invalid_uri_returns_empty(self, library):
        assert library.browse("spotify:track:123") == []

    def test_known_summary_calls_api(self, library):
        artist = MagicMock()
        artist.id = "1"
        artist.name = "A"
        artist.image = MagicMock(return_value="https://img.jpg")
        library.backend.session.get_user_artists.return_value = [artist]

        with patch("mopidy_tidal.library.model_factory_map") as mock_mfm:
            mock_model = MagicMock()
            mock_model.ref = Ref.artist(uri="tidal:artist:1", name="A")
            mock_mfm.return_value = iter([mock_model])
            refs = library.browse("tidal:my_artists")
            assert len(refs) == 1


class TestLibraryLookup:
    def test_single_uri_string(self, library):
        mock_model = MagicMock()
        mock_track = MagicMock()
        mock_track.full = "full_track"
        mock_model.tracks.return_value = [mock_track]

        with patch("mopidy_tidal.library.lookup_uri", return_value=mock_model):
            result = library.lookup("tidal:track:1")
            assert result == ["full_track"]

    def test_invalid_uri_skipped(self, library):
        with patch("mopidy_tidal.library.lookup_uri", side_effect=ValueError):
            result = library.lookup("tidal:bogus:1")
            assert result == []


class TestLibraryGetImages:
    def test_returns_images(self, library):
        mock_model = MagicMock()
        mock_model.images = ["img1"]

        with patch("mopidy_tidal.library.lookup_uri", return_value=mock_model):
            result = library.get_images(["tidal:track:1"])
            assert result == {"tidal:track:1": ["img1"]}

    def test_invalid_uri_returns_empty(self, library):
        with patch("mopidy_tidal.library.lookup_uri", side_effect=ValueError):
            result = library.get_images(["tidal:bogus:1"])
            assert result == {"tidal:bogus:1": []}


class TestLibraryGetDistinct:
    def test_artist_field_no_query(self, library):
        a = MagicMock()
        a.name = "Radiohead"
        library.backend.session.get_user_artists.return_value = [a]
        result = library.get_distinct("artist")
        assert len(result) == 1
        assert "Radiohead" in result[0]

    def test_album_field_no_query(self, library):
        a = MagicMock()
        a.name = "OK Computer"
        library.backend.session.get_user_albums.return_value = [a]
        result = library.get_distinct("album")
        assert len(result) == 1
        assert "OK Computer" in result[0]

    def test_track_field_no_query(self, library):
        t = MagicMock()
        t.name = "Creep"
        library.backend.session.get_user_tracks.return_value = [t]
        result = library.get_distinct("track")
        assert len(result) == 1
        assert "Creep" in result[0]

    def test_unknown_field_returns_empty(self, library):
        assert library.get_distinct("genre") == []

    def test_with_query_delegates_to_search(self, library):
        with patch("mopidy_tidal.library.tidal_search") as mock_search:
            mock_search.return_value = {"artists": []}
            result = library.get_distinct("artist", query={"any": ["test"]})
            mock_search.assert_called_once()
            assert result == []


class TestLibrarySearch:
    def test_delegates_to_tidal_search(self, library):
        with patch("mopidy_tidal.library.tidal_search") as mock_search:
            mock_search.return_value = {"tracks": [], "albums": []}
            result = library.search(query={"any": ["test"]}, exact=False)
            mock_search.assert_called_once()
            assert isinstance(result, SearchResult)


class TestLibraryBrowseFallback:
    def test_browse_entity_uri_calls_lookup(self, library):
        mock_model = MagicMock()
        mock_ref = Ref.track(uri="tidal:track:1", name="T")
        mock_item = MagicMock()
        mock_item.ref = mock_ref
        mock_model.items.return_value = [mock_item]

        with patch("mopidy_tidal.library.lookup_uri", return_value=mock_model):
            refs = library.browse("tidal:album:42")
            assert len(refs) == 1
            assert refs[0].name == "T"

    def test_browse_entity_uri_error_returns_empty(self, library):
        with patch("mopidy_tidal.library.lookup_uri", side_effect=ValueError):
            assert library.browse("tidal:album:42") == []
