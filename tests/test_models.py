from __future__ import annotations

from unittest.mock import MagicMock

import mopidy.models as mm
import pytest
import tidalapi as tdl

from mopidy_tidal.tidal import cache
from mopidy_tidal.tidal.build import (
    _year,
    build_album,
    build_artist,
    build_playlist,
    build_playlist_as_album,
    build_track,
    build_tracks,
)
from mopidy_tidal.tidal.refs import album_ref, artist_ref, playlist_ref, ref_for, refs_for, track_ref


@pytest.fixture(autouse=True)
def _clear_caches():
    cache.clear()
    yield
    cache.clear()


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


# -- _year helper ---------------------------------------------------------


class TestYear:
    def test_extracts_year(self):
        assert _year("2024-01-15") == "2024"

    def test_short_string(self):
        assert _year("20") is None

    def test_none(self):
        assert _year(None) is None

    def test_empty(self):
        assert _year("") is None


# -- refs -----------------------------------------------------------------


class TestRefs:
    def test_track_ref(self):
        ref = track_ref(_fake_track("77", "Paranoid Android"))
        assert ref.uri == "tidal:track:77"
        assert ref.name == "Paranoid Android"
        assert ref.type == "track"

    def test_album_ref(self):
        ref = album_ref(_fake_album("55", "OK Computer"))
        assert ref.uri == "tidal:album:55"
        assert ref.name == "OK Computer"
        assert ref.type == "album"

    def test_artist_ref(self):
        ref = artist_ref(_fake_artist("42", "Radiohead"))
        assert ref.uri == "tidal:artist:42"
        assert ref.name == "Radiohead"
        assert ref.type == "artist"

    def test_playlist_ref(self):
        ref = playlist_ref(_fake_playlist("400", "My Playlist"))
        assert ref.uri == "tidal:playlist:400"
        assert ref.name == "My Playlist"
        assert ref.type == "playlist"


class TestRefFor:
    def test_track(self):
        ref = ref_for(_fake_track("1", "T"))
        assert ref.type == "track"

    def test_album(self):
        ref = ref_for(_fake_album("2", "A"))
        assert ref.type == "album"

    def test_artist(self):
        ref = ref_for(_fake_artist("3", "Ar"))
        assert ref.type == "artist"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="No ref mapping"):
            ref_for("not a tidal object")

    def test_video_returns_none(self):
        video = MagicMock(spec=tdl.Video)
        assert ref_for(video) is None


class TestRefsFor:
    def test_yields_refs(self):
        items = [_fake_track("1", "T"), _fake_artist("2", "A")]
        results = refs_for(items)
        assert len(results) == 2

    def test_skips_unknown(self):
        items = [_fake_track("1", "T"), "garbage", _fake_artist("2", "A")]
        results = refs_for(items)
        assert len(results) == 2

    def test_skips_video(self):
        video = MagicMock(spec=tdl.Video)
        items = [video, _fake_track("1", "T")]
        results = refs_for(items)
        assert len(results) == 1


# -- build ----------------------------------------------------------------


class TestBuildArtist:
    def test_basic(self):
        result = build_artist(_fake_artist("42", "Radiohead"))
        assert isinstance(result, mm.Artist)
        assert result.uri == "tidal:artist:42"
        assert result.name == "Radiohead"

    def test_cached(self):
        a = _fake_artist("42", "Radiohead")
        r1 = build_artist(a)
        r2 = build_artist(a)
        assert r1 is r2


class TestBuildAlbum:
    def test_basic(self):
        result = build_album(_fake_album("55", "OK Computer"))
        assert isinstance(result, mm.Album)
        assert result.uri == "tidal:album:55"
        assert result.num_tracks == 10
        assert result.date == "2024"
        assert len(result.artists) == 1

    def test_cached(self):
        a = _fake_album("55", "OK Computer")
        r1 = build_album(a)
        r2 = build_album(a)
        assert r1 is r2


class TestBuildTrack:
    def test_basic(self):
        result = build_track(_fake_track("77", "Paranoid Android"))
        assert isinstance(result, mm.Track)
        assert result.uri == "tidal:track:77"
        assert result.length == 240_000
        assert result.track_no == 1
        assert result.disc_no == 1
        assert result.album is not None
        assert len(result.artists) == 1

    def test_cached(self):
        t = _fake_track("77", "Paranoid Android")
        r1 = build_track(t)
        r2 = build_track(t)
        assert r1 is r2

    def test_no_album(self):
        t = _fake_track("77", "Paranoid Android")
        t.album = None
        result = build_track(t)
        assert result.album is None

    def test_no_artists(self):
        t = _fake_track("77", "Paranoid Android")
        t.artists = []
        result = build_track(t)
        assert list(result.artists) == []


class TestBuildTracks:
    def test_bulk(self):
        tracks = [_fake_track(str(i), f"Track {i}") for i in range(5)]
        results = build_tracks(tracks)
        assert len(results) == 5
        assert all(isinstance(r, mm.Track) for r in results)


class TestBuildPlaylist:
    def test_basic(self):
        p = _fake_playlist("400", "My Playlist")
        tracks = [build_track(_fake_track(str(i), f"T{i}")) for i in range(3)]
        result = build_playlist(p, tracks)
        assert isinstance(result, mm.Playlist)
        assert result.uri == "tidal:playlist:400"
        assert result.name == "My Playlist"
        assert len(result.tracks) == 3


class TestBuildPlaylistAsAlbum:
    def test_basic(self):
        p = _fake_playlist("400", "My Playlist")
        result = build_playlist_as_album(p)
        assert isinstance(result, mm.Album)
        assert result.uri == "tidal:playlist:400"
        assert result.name == "My Playlist"


# -- images ---------------------------------------------------------------


class TestTrackImages:
    """Mopidy requests images for tracks; a track's cover comes from its
    album. The album on session.track() is NOT cover-hydrated, so the cover is
    resolved by fetching the album (get_album includes coverArt). Results are
    cached per URI and the album cover is cached per album URI.
    """

    def _session(self):
        session = MagicMock()
        track = MagicMock()
        track.album = MagicMock()
        track.album.id = "55"
        # track.album itself has NO usable cover (matches live behaviour).
        track.album.cover.return_value = ""
        session.track.return_value = track

        resolved = MagicMock()
        resolved.cover.return_value = "https://img/cover.jpg"
        session.album.return_value = resolved
        return session

    def test_track_image_is_album_cover(self):
        from mopidy_tidal.tidal.images import get_images

        imgs = get_images(self._session(), "tidal:track:1")
        assert [i.uri for i in imgs] == ["https://img/cover.jpg"]

    def test_cover_resolved_by_album_fetch(self):
        from mopidy_tidal.tidal.images import get_images

        session = self._session()
        get_images(session, "tidal:track:1")
        # The cover comes from the cover-hydrated album fetch, since
        # track.album carries none.
        session.album.assert_called_once_with("55")

    def test_result_is_cached_per_uri(self):
        from mopidy_tidal.tidal.images import get_images

        session = self._session()
        get_images(session, "tidal:track:1")
        get_images(session, "tidal:track:1")
        session.track.assert_called_once()

    def test_no_album_yields_no_images(self):
        from mopidy_tidal.tidal.images import get_images

        session = self._session()
        session.track.return_value.album = None
        assert get_images(session, "tidal:track:1") == []
        session.album.assert_not_called()


class TestBatchImages:
    """A page of track URIs must collapse to grouped API calls (one
    get_tracks + one get_albums), not a request per track — that is what
    avoids TIDAL rate-limiting.
    """

    def _track(self, track_id, album_id):
        t = MagicMock()
        t.id = track_id
        t.album = MagicMock()
        t.album.id = album_id
        return t

    def _album(self, album_id, cover):
        a = MagicMock()
        a.id = album_id
        a.cover.return_value = cover
        return a

    def test_page_uses_two_grouped_calls(self):
        from mopidy_tidal.tidal.images import get_images_batch

        session = MagicMock()
        # Three tracks across two albums.
        session.get_tracks.return_value = [self._track("1", "100"), self._track("2", "100"), self._track("3", "200")]
        session.get_albums.return_value = [
            self._album("100", "https://img/100.jpg"),
            self._album("200", "https://img/200.jpg"),
        ]

        uris = ["tidal:track:1", "tidal:track:2", "tidal:track:3"]
        result = get_images_batch(session, uris)

        # Exactly one batched track fetch and one batched album fetch.
        session.get_tracks.assert_called_once_with(track_ids=["1", "2", "3"])
        session.get_albums.assert_called_once()
        assert [i.uri for i in result["tidal:track:1"]] == ["https://img/100.jpg"]
        assert [i.uri for i in result["tidal:track:2"]] == ["https://img/100.jpg"]
        assert [i.uri for i in result["tidal:track:3"]] == ["https://img/200.jpg"]

    def test_cache_hits_skip_the_batch(self):
        from mopidy_tidal.tidal import cache
        from mopidy_tidal.tidal.images import get_images_batch

        cache.put_images("tidal:track:1", ["cached"])
        session = MagicMock()
        session.get_tracks.return_value = [self._track("2", "100")]
        session.get_albums.return_value = [self._album("100", "https://img/100.jpg")]

        result = get_images_batch(session, ["tidal:track:1", "tidal:track:2"])

        assert result["tidal:track:1"] == ["cached"]
        # Only the uncached track is fetched.
        session.get_tracks.assert_called_once_with(track_ids=["2"])

    def test_empty_page(self):
        from mopidy_tidal.tidal.images import get_images_batch

        assert get_images_batch(MagicMock(), []) == {}
