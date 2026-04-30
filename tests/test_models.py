from __future__ import annotations

from unittest.mock import MagicMock

import mopidy.models as mm
import pytest
import tidalapi as tdl

from mopidy_tidal.cache import _model_cache
from mopidy_tidal.models import lookup_uri, model_factory, model_factory_map
from mopidy_tidal.models._base import Model, _year_from
from mopidy_tidal.models.album import Album
from mopidy_tidal.models.artist import Artist
from mopidy_tidal.models.track import Track


@pytest.fixture(autouse=True)
def _clear_caches():
    _model_cache.clear()
    yield
    _model_cache.clear()


# -- helpers --------------------------------------------------------------


def _fake_artist(id="100", name="Test Artist"):
    a = MagicMock(spec=tdl.Artist)
    a.id = id
    a.name = name
    a.profile = MagicMock(return_value="https://img/artist.jpg")
    a.radio = []
    return a


def _fake_album(id="200", name="Test Album", artists=None):
    a = MagicMock(spec=tdl.Album)
    a.id = id
    a.name = name
    a.artists = artists or [_fake_artist()]
    a.num_tracks = 10
    a.num_volumes = 1
    a.release_date = "2024-01-15"
    a.cover = MagicMock(return_value="https://img/album.jpg")
    a.tracks = MagicMock(return_value=[])
    return a


def _fake_track(id="300", name="Test Track", audio_quality="HIGH"):
    t = MagicMock(spec=tdl.Track)
    t.id = id
    t.name = name
    t.audio_quality = audio_quality
    t.artists = [_fake_artist()]
    t.album = _fake_album()
    t.track_num = 1
    t.duration = 240
    t.volume_num = 1
    t.media_tags = ["LOSSLESS"]
    t.similar_tracks = MagicMock(return_value=[])
    return t


def _fake_playlist(id="400", name="Test Playlist"):
    p = MagicMock(spec=tdl.Playlist)
    p.id = id
    p.name = name
    p.num_tracks = 5
    p.last_updated = "2024-06-01T00:00:00"
    p.created = "2024-01-01"
    p.cover = MagicMock(return_value="https://img/playlist.jpg")
    p.tracks = MagicMock(return_value=[])
    return p


# -- _base helpers --------------------------------------------------------


class TestYearFrom:
    def test_extracts_year(self):
        assert _year_from("2024-01-15") == "2024"

    def test_short_string(self):
        assert _year_from("20") is None

    def test_none(self):
        assert _year_from(None) is None

    def test_empty(self):
        assert _year_from("") is None



class TestModelBase:
    def test_ref_and_api(self):
        ref = mm.Ref.track(uri="tidal:track:1", name="T")
        m = Model(ref=ref, api="api_obj")
        assert m.uri == "tidal:track:1"
        assert m.name == "T"
        assert m.api == "api_obj"

    def test_full_lazy(self):
        ref = mm.Ref.track(uri="tidal:track:1", name="T")
        m = Model(ref=ref, api=None)
        m.build = MagicMock(return_value="built")
        assert m.full == "built"
        assert m.full == "built"  # cached
        m.build.assert_called_once()

    def test_extra_kwargs(self):
        ref = mm.Ref.track(uri="tidal:track:1", name="T")
        m = Model(ref=ref, api=None, foo="bar")
        assert m.foo == "bar"


# -- Artist ---------------------------------------------------------------


class TestArtist:
    def test_from_api(self):
        a = Artist.from_api(_fake_artist("42", "Radiohead"))
        assert a.uri == "tidal:artist:42"
        assert a.name == "Radiohead"
        assert a.ref.type == "artist"

    def test_build(self):
        a = Artist.from_api(_fake_artist("42", "Radiohead"))
        full = a.build()
        assert isinstance(full, mm.Artist)
        assert full.uri == "tidal:artist:42"
        assert full.name == "Radiohead"

    def test_images(self):
        a = Artist.from_api(_fake_artist())
        imgs = a.images
        assert len(imgs) == 1
        assert "artist" in imgs[0].uri or "img" in imgs[0].uri


# -- Album ----------------------------------------------------------------


class TestAlbum:
    def test_from_api(self):
        artist = _fake_artist("10", "Artist")
        alb = Album.from_api(_fake_album("55", "OK Computer", [artist]))
        assert alb.uri == "tidal:album:55"
        assert alb.name == "OK Computer"
        assert alb.ref.type == "album"
        assert len(alb.artists) == 1

    def test_build(self):
        alb = Album.from_api(_fake_album("55", "OK Computer"))
        full = alb.build()
        assert isinstance(full, mm.Album)
        assert full.num_tracks == 10
        assert full.date == "2024"

    def test_images(self):
        alb = Album.from_api(_fake_album())
        imgs = alb.images
        assert len(imgs) == 1


# -- Track ----------------------------------------------------------------


class TestTrack:
    def test_from_api(self):
        t = Track.from_api(_fake_track("77", "Paranoid Android"))
        assert t.uri == "tidal:track:77"
        assert t.name == "Paranoid Android"
        assert t.ref.type == "track"
        assert t.album is not None
        assert len(t.artists) == 1

    def test_build(self):
        t = Track.from_api(_fake_track("77", "Paranoid Android"))
        full = t.build()
        assert isinstance(full, mm.Track)
        assert full.length == 240_000
        assert full.track_no == 1

    def test_tracks_returns_self(self):
        t = Track.from_api(_fake_track())
        assert t.tracks() == [t]

    def test_items_raises(self):
        t = Track.from_api(_fake_track())
        with pytest.raises(AttributeError):
            t.items()


# -- model_factory --------------------------------------------------------


class TestModelFactory:
    def test_track(self):
        m = model_factory(_fake_track("1", "T"))
        assert isinstance(m, Track)

    def test_album(self):
        m = model_factory(_fake_album("2", "A"))
        assert isinstance(m, Album)

    def test_artist(self):
        m = model_factory(_fake_artist("3", "Ar"))
        assert isinstance(m, Artist)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="No model for"):
            model_factory("not a tidal object")


class TestModelFactoryMap:
    def test_yields_models(self):
        items = [_fake_track("1", "T"), _fake_artist("2", "A")]
        results = list(model_factory_map(items))
        assert len(results) == 2

    def test_skips_unknown(self):
        items = [_fake_track("1", "T"), "garbage", _fake_artist("2", "A")]
        results = list(model_factory_map(items))
        assert len(results) == 2

    def test_skips_video(self):
        video = MagicMock(spec=tdl.Video)
        items = [video, _fake_track("1", "T")]
        results = list(model_factory_map(items))
        assert len(results) == 1


# -- lookup_uri -----------------------------------------------------------


class TestLookupUri:
    def test_track(self):
        session = MagicMock()
        fake = MagicMock()
        fake.id = "88"
        fake.name = "Looked Up"
        fake.media_tags = ["LOSSLESS"]
        fake.artists = []
        fake.album = None
        session.track.return_value = fake
        m = lookup_uri(session, "tidal:track:88")
        assert isinstance(m, Track)
        session.track.assert_called_once_with("88")

    def test_unknown_type_raises(self):
        session = MagicMock()
        with pytest.raises(ValueError, match="No model for uri"):
            lookup_uri(session, "tidal:directory")

    def test_invalid_uri_raises(self):
        session = MagicMock()
        with pytest.raises(ValueError):
            lookup_uri(session, "spotify:track:123")
