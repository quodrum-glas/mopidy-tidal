from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from mopidy.models import Ref, SearchResult

from mopidy_tidal.library import TidalLibraryProvider
from mopidy_tidal.playback import TidalPlaybackProvider
from mopidy_tidal.uri import URI, URIType


# -- Playback -------------------------------------------------------------


@pytest.fixture()
def playback():
    p = TidalPlaybackProvider.__new__(TidalPlaybackProvider)
    p.backend = MagicMock()
    p._TidalPlaybackProvider__cache = {}  # fresh instance-level cache
    return p


class TestPlaybackTranslateUri:
    def test_bts_manifest(self, playback):
        stream = MagicMock()
        stream.manifest_mime_type = "application/vnd.tidal.bts"
        stream.audio_quality = "LOSSLESS"
        stream.codec = "FLAC"
        stream.bit_depth = 16
        stream.sample_rate = 44100
        manifest = MagicMock()
        manifest.get_urls.return_value = ["https://stream.tidal.com/track.flac"]
        stream.get_stream_manifest.return_value = manifest
        playback.backend.session.get_stream.return_value = stream

        url = playback.translate_uri("tidal:track:123")
        assert url == "https://stream.tidal.com/track.flac"

    def test_bts_no_urls_returns_none(self, playback):
        stream = MagicMock()
        stream.manifest_mime_type = "application/vnd.tidal.bts"
        stream.audio_quality = "HIGH"
        stream.codec = "AAC"
        stream.bit_depth = 16
        stream.sample_rate = 44100
        manifest = MagicMock()
        manifest.get_urls.return_value = []
        stream.get_stream_manifest.return_value = manifest
        playback.backend.session.get_stream.return_value = stream

        assert playback.translate_uri("tidal:track:456") is None

    def test_unknown_manifest_returns_none(self, playback):
        stream = MagicMock()
        stream.manifest_mime_type = "application/unknown"
        stream.audio_quality = "HIGH"
        stream.codec = "AAC"
        stream.bit_depth = 16
        stream.sample_rate = 44100
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
        library.backend.session.user.favorites.artists.return_value = [artist]

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
        library.backend.session.user.favorites.artists.return_value = [a]
        result = library.get_distinct("artist")
        assert len(result) == 1
        assert "Radiohead" in result[0]

    def test_unknown_field_returns_empty(self, library):
        assert library.get_distinct("genre") == []
