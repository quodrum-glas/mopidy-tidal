from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mopidy.models import Playlist, Ref, Track

from mopidy_tidal.playlists import TidalPlaylistsProvider, _empty


@pytest.fixture()
def backend():
    b = MagicMock()
    b.session = MagicMock()
    b.logged_in = True
    return b


@pytest.fixture()
def provider(backend):
    with patch.object(TidalPlaylistsProvider, "__init__", lambda self, *a, **kw: None):
        p = TidalPlaylistsProvider.__new__(TidalPlaylistsProvider)
    p.backend = backend
    from cachetools import TTLCache

    p._TidalPlaylistsProvider__as_list_cache = TTLCache(maxsize=1, ttl=60)
    p._injected_actions = {"radio": p._get_radio}
    p._injected = {name: _empty(name) for name in p._injected_actions}
    return p


def _pl(uri: str, name: str = "test", tracks: list | None = None) -> Playlist:
    return Playlist(uri=uri, name=name, tracks=tracks or [], last_modified=0)


def _track(uri: str, name: str = "t") -> Track:
    return Track(uri=uri, name=name)


# -- _empty ---------------------------------------------------------------


class TestEmpty:
    def test_creates_playlist_with_name_as_id(self):
        pl = _empty("radio")
        assert pl.uri == "tidal:playlist:radio"
        assert pl.name == "radio"
        assert pl.tracks == ()


# -- intercept decorator: lookup ------------------------------------------


class TestInterceptLookup:
    def test_injected_uri_returns_injected_playlist(self, provider):
        provider._injected["radio"] = _pl("tidal:playlist:radio", "radio")
        result = provider.lookup("tidal:playlist:radio")
        assert result.name == "radio"

    def test_non_injected_falls_through(self, provider):
        with patch("mopidy_tidal.playlists.lookup_uri") as mock_lookup:
            mock_lookup.return_value = MagicMock(full=_pl("tidal:playlist:999", "real"))
            result = provider.lookup("tidal:playlist:999")
            assert result.name == "real"
            mock_lookup.assert_called_once()

    def test_non_playlist_uri_falls_through(self, provider):
        with patch("mopidy_tidal.playlists.lookup_uri") as mock_lookup:
            mock_lookup.return_value = MagicMock(full=_pl("tidal:album:1", "alb"))
            provider.lookup("tidal:album:1")
            mock_lookup.assert_called_once()


# -- intercept decorator: get_items ---------------------------------------


class TestInterceptGetItems:
    def test_injected_returns_refs(self, provider):
        tracks = [_track("tidal:track:1", "A"), _track("tidal:track:2", "B")]
        provider._injected["radio"] = _pl("tidal:playlist:radio", "radio", tracks)
        refs = provider.get_items("tidal:playlist:radio")
        assert len(refs) == 2
        assert all(isinstance(r, Ref) for r in refs)
        assert refs[0].name == "A"

    def test_non_injected_falls_through(self, provider):
        mock_model = MagicMock()
        mock_model.tracks.return_value = []
        with patch("mopidy_tidal.playlists.lookup_uri", return_value=mock_model):
            provider.get_items("tidal:playlist:999")
            mock_model.tracks.assert_called_once()


# -- intercept decorator: save --------------------------------------------


class TestInterceptSave:
    def test_injected_calls_action_and_stores(self, provider):
        new_pl = _pl("tidal:playlist:radio", "radio: Song", [_track("tidal:track:5")])
        provider._injected_actions["radio"] = MagicMock(return_value=new_pl)
        result = provider.save(_pl("tidal:playlist:radio", "radio"))
        assert result is new_pl
        assert provider._injected["radio"] is new_pl

    def test_injected_action_returns_none_keeps_old(self, provider):
        old = provider._injected["radio"]
        provider._injected_actions["radio"] = MagicMock(return_value=None)
        result = provider.save(_pl("tidal:playlist:radio"))
        assert result is None
        assert provider._injected["radio"] is old


# -- _get_radio -----------------------------------------------------------


class TestGetRadio:
    def test_no_tracks_returns_none(self, provider):
        result = provider._get_radio(_pl("tidal:playlist:radio"))
        assert result is None

    def test_generates_radio_from_last_track(self, provider):
        seed_track = _track("tidal:track:42", "Seed")
        pl = _pl("tidal:playlist:radio", "radio", [seed_track])

        mock_model = MagicMock()
        mock_model.name = "Seed"
        radio_track = MagicMock()
        radio_track.full = _track("tidal:track:99", "Radio Track")
        mock_model.radio.return_value = [radio_track]

        with patch("mopidy_tidal.playlists.lookup_uri", return_value=mock_model):
            result = provider._get_radio(pl)

        assert result.name == "radio: Seed"
        assert len(result.tracks) == 1


# -- create ---------------------------------------------------------------


class TestCreate:
    def test_creates_and_clears_cache(self, provider, backend):
        api_pl = MagicMock()
        api_pl.id = "new123"
        backend.session.create_playlist.return_value = api_pl

        result = provider.create("My New Playlist")
        assert result.uri == "tidal:playlist:new123"
        assert result.name == "My New Playlist"
        backend.session.create_playlist.assert_called_once_with("My New Playlist")


# -- delete ---------------------------------------------------------------


class TestDelete:
    def test_deletes_playlist(self, provider, backend):
        ok = provider.delete("tidal:playlist:abc")
        assert ok is True
        backend.session.delete_playlist.assert_called_once_with("abc")

    def test_returns_false_for_non_playlist(self, provider):
        assert provider.delete("tidal:album:123") is False

    def test_returns_false_on_api_failure(self, provider, backend):
        backend.session.delete_playlist.side_effect = RuntimeError("fail")
        assert provider.delete("tidal:playlist:abc") is False


# -- refresh --------------------------------------------------------------


class TestRefresh:
    def test_clears_cache(self, provider):
        provider._TidalPlaylistsProvider__as_list_cache["key"] = "val"
        provider.refresh()
        assert len(provider._TidalPlaylistsProvider__as_list_cache) == 0


# -- as_list --------------------------------------------------------------


class TestAsList:
    def test_returns_refs_from_session(self, provider, backend):
        mock_pl = MagicMock()
        mock_pl.id = "pl1"
        mock_pl.name = "My Playlist"
        backend.session.get_user_playlists.return_value = [mock_pl]

        with patch("mopidy_tidal.playlists.model_factory_map") as mock_mfm:
            mock_model = MagicMock()
            mock_model.ref = Ref.playlist(uri="tidal:playlist:pl1", name="My Playlist")
            mock_mfm.return_value = iter([mock_model])
            refs = provider.as_list()
            # Should include the real playlist + injected playlists
            assert len(refs) >= 1


# -- _create / _add_tracks / _remove_tracks --------------------------------


class TestCrudHelpers:
    def test_create_with_tracks_calls_add(self, provider, backend):
        api_pl = MagicMock()
        api_pl.id = "new1"
        backend.session.create_playlist.return_value = api_pl

        pl = _pl("tidal:playlist:new1", "New", [_track("tidal:track:1")])
        with patch.object(provider, "_add_tracks") as mock_add:
            provider._create(pl)
            mock_add.assert_called_once()

    def test_add_tracks_calls_session(self, provider, backend):
        provider._add_tracks("tidal:playlist:abc", ["tidal:track:1", "tidal:track:2"])
        backend.session.add_tracks_to_playlist.assert_called_once_with(
            "abc", ["1", "2"]
        )

    def test_remove_tracks_calls_session(self, provider, backend):
        provider._remove_tracks("tidal:playlist:abc", {"tidal:track:3"})
        backend.session.remove_tracks_from_playlist.assert_called_once_with(
            "abc", ["3"]
        )


# -- save (non-injected) --------------------------------------------------


class TestSave:
    def test_creates_when_lookup_returns_none(self, provider, backend):
        with (
            patch.object(provider, "lookup", return_value=None),
            patch.object(
                provider, "_create", return_value=_pl("tidal:playlist:new"),
            ) as mock_create,
        ):
            provider.save(_pl("tidal:playlist:new", "New"))
            mock_create.assert_called_once()

    def test_adds_new_tracks(self, provider, backend):
        old = _pl("tidal:playlist:1", "P", [_track("tidal:track:1")])
        new = _pl("tidal:playlist:1", "P", [_track("tidal:track:1"), _track("tidal:track:2")])
        with patch.object(provider, "lookup", return_value=old), \
             patch.object(provider, "_add_tracks") as mock_add:
            provider.save(new)
            mock_add.assert_called_once()
            added_uris = mock_add.call_args[0][1]
            assert "tidal:track:2" in added_uris

    def test_removes_old_tracks(self, provider, backend):
        old = _pl("tidal:playlist:1", "P", [_track("tidal:track:1"), _track("tidal:track:2")])
        new = _pl("tidal:playlist:1", "P", [_track("tidal:track:1")])
        with patch.object(provider, "lookup", return_value=old), \
             patch.object(provider, "_remove_tracks") as mock_rm:
            provider.save(new)
            mock_rm.assert_called_once()
            removed_uris = mock_rm.call_args[0][1]
            assert "tidal:track:2" in removed_uris
