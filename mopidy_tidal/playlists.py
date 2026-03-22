from __future__ import annotations

"""Playlists provider: list, lookup, save, delete, injected playlists."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from cachetools import TTLCache, cachedmethod
from mopidy.backend import PlaylistsProvider
from mopidy.models import Playlist, Ref

from mopidy_tidal.display import alert_item, tidal_item
from mopidy_tidal.models import lookup_uri, model_factory_map
from mopidy_tidal.uri import URI, URIType

logger = logging.getLogger(__name__)


def _intercept_injected(fn):
    """Route injected playlist URIs — save calls action & stores, lookup/get_items read state."""
    @wraps(fn)
    def wrapper(self, uri_or_playlist: str | Playlist, *args: Any, **kwargs: Any) -> Any:
        uri = uri_or_playlist.uri if isinstance(uri_or_playlist, Playlist) else uri_or_playlist
        parsed = URI.from_string(uri)
        name = parsed.id if parsed.type == URIType.PLAYLIST else None
        if name not in self._injected:
            return fn(self, uri_or_playlist, *args, **kwargs)
        if fn.__name__ == "save":
            result = self._injected_actions[name](uri_or_playlist)
            if result is not None:
                self._injected[name] = result
            return result
        if fn.__name__ == "lookup":
            return self._injected[name]
        if fn.__name__ == "get_items":
            return [Ref.track(uri=t.uri, name=t.name) for t in self._injected[name].tracks]
        return fn(self, uri_or_playlist, *args, **kwargs)
    return wrapper


class TidalPlaylistsProvider(PlaylistsProvider):

    def __init__(self, *args: object, playlist_cache_ttl: int, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.__as_list_cache: TTLCache = TTLCache(maxsize=1, ttl=playlist_cache_ttl)
        self._injected_actions: dict[str, Callable] = {
            "radio": self._get_radio,
        }
        self._injected: dict[str, Playlist] = {
            name: _empty(name) for name in self._injected_actions
        }

    # -- list / browse ----------------------------------------------------

    @cachedmethod(lambda self: self.__as_list_cache)
    def as_list(self) -> list[Ref]:
        session = self.backend.session
        results = session.user.favorites.playlists()
        return [
            *(
                m.ref.replace(name=tidal_item(m.ref.name))
                for m in model_factory_map(results)
            ),
            *(
                Ref.playlist(uri=pl.uri, name=tidal_item(alert_item(pl.name)))
                for pl in self._injected.values()
            ),
        ]

    @_intercept_injected
    def get_items(self, uri: str) -> list[Ref] | None:
        return [t.ref for t in lookup_uri(self.backend.session, uri).tracks()]

    # -- lookup -----------------------------------------------------------

    @_intercept_injected
    def lookup(self, uri: str) -> Playlist | None:
        return lookup_uri(self.backend.session, uri).full

    # -- save / create / delete -------------------------------------------

    @_intercept_injected
    def save(self, playlist: Playlist) -> Playlist | None:
        old = self.lookup(playlist.uri)
        if old is None:
            return self._create(playlist)

        new_uris = [t.uri for t in playlist.tracks]
        old_uris_set = {t.uri for t in old.tracks}
        to_add = [u for u in new_uris if u not in old_uris_set]
        new_uris_set = set(new_uris)
        to_remove = {t.uri for t in old.tracks if t.uri not in new_uris_set}
        if to_add:
            self._add_tracks(playlist.uri, to_add)
        if to_remove:
            self._remove_tracks(playlist.uri, to_remove, old)
        return playlist

    def create(self, name: str) -> Playlist | None:
        api_playlist = self.backend.session.user.create_playlist(name)
        uri = str(URI(URIType.PLAYLIST, api_playlist.id))
        logger.info("Created playlist: %s (%s)", name, uri)
        self.__as_list_cache.clear()
        return Playlist(uri=uri, name=name, tracks=[], last_modified=0)

    def delete(self, uri: str) -> bool:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.PLAYLIST or not parsed.id:
            return False
        trn = f"trn:playlist:{parsed.id}"
        ok = self.backend.session.playlist_folders.remove([trn])
        if ok:
            logger.info("Deleted playlist: %s", uri)
            self.__as_list_cache.clear()
        return ok

    def refresh(self) -> None:
        self.__as_list_cache.clear()

    # -- injected playlist actions ----------------------------------------

    def _get_radio(self, playlist: Playlist) -> Playlist | None:
        seed = playlist.tracks[-1] if playlist.tracks else None
        if not seed:
            return None

        track = lookup_uri(self.backend.session, seed.uri)
        logger.info("Generating radio from: %s", track.name)
        return playlist.replace(
            name=f"radio: {track.name}",
            tracks=[t.full for t in track.radio()],
        )

    # -- CRUD helpers -----------------------------------------------------

    def _create(self, playlist: Playlist) -> Playlist:
        created = self.create(playlist.name)
        if created and playlist.tracks:
            self._add_tracks(created.uri, {t.uri for t in playlist.tracks})
        return created or playlist

    def _add_tracks(self, uri: str, track_uris: list[str] | set[str]) -> None:
        parsed = URI.from_string(uri)
        api_playlist = self.backend.session.playlist(parsed.id)
        track_ids = [URI.from_string(t).track for t in track_uris]
        logger.info("Adding %d tracks to %s", len(track_ids), uri)
        api_playlist.add(track_ids)

    def _remove_tracks(self, uri: str, track_uris: set[str], old: Playlist) -> None:
        remove_uris = set(track_uris)
        indices = [i for i, t in enumerate(old.tracks) if t.uri in remove_uris]
        if not indices:
            return
        parsed = URI.from_string(uri)
        api_playlist = self.backend.session.playlist(parsed.id)
        for idx in sorted(indices, reverse=True):
            logger.info("Removing track at index %d from %s", idx, uri)
            api_playlist.remove_by_index(idx)


def _empty(name: str) -> Playlist:
    return Playlist(uri=str(URI(URIType.PLAYLIST, name)), name=name, tracks=[], last_modified=0)
