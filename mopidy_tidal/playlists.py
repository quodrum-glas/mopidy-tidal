from __future__ import unicode_literals

import logging
from typing import Iterable, List, Optional

from cachetools import cached, TTLCache, cachedmethod
from mopidy.backend import PlaylistsProvider
from mopidy.models import Playlist, Ref, Track

from mopidy_tidal.display import tidal_item, alert_item
from mopidy_tidal.models import lookup_uri, model_factory_map
from mopidy_tidal.uri import URI, URIType
from mopidy_tidal.workers import sorted_threaded

logger = logging.getLogger(__name__)


class TidalPlaylistsProvider(PlaylistsProvider):
    NEW_PLAYLIST_URI = f"{URI(URIType.PLAYLIST, 'new')}"
    INJECTED_PLAYLISTS = {
        name: Playlist(
            uri=f"{URI(URIType.PLAYLIST, name)}",
            name=name,
            tracks=[],
            last_modified=0
        ) for name in ["radio", "mix"]
    }

    def __init__(self, *args, playlist_cache_ttl, **kwargs):
        super().__init__(*args, **kwargs)
        self.__as_list_cache = TTLCache(maxsize=1, ttl=playlist_cache_ttl)

    @cachedmethod(lambda self: self.__as_list_cache)
    def as_list(self) -> List[Ref]:
        """
        Get a list of the currently available playlists.

        Returns a list of :class:`~mopidy.models.Ref` objects referring to the
        playlists. In other words, no information about the playlists' content
        is given.

        :rtype: list of :class:`mopidy.models.Ref`

        .. versionadded:: 1.0
        """
        logger.debug("TidalPlaylistsProvider.as_list() ttl: %s", self.as_list.cache(self).ttl)
        results = sorted_threaded(
            self.backend.session.user.playlist_and_favorite_playlists,
        )
        return [
            *(m.ref.replace(name=tidal_item(m.ref.name))
              for m in model_factory_map(i for items in results for i in items)),
            *(Ref.playlist(uri=p.uri, name=tidal_item(alert_item(p.name)))
              for p in self.INJECTED_PLAYLISTS.values()),
        ]

    def get_items(self, uri: str) -> Optional[List[Ref]]:
        """
        Get the items in a playlist specified by ``uri``.

        Returns a list of :class:`~mopidy.models.Ref` objects referring to the
        playlist's items.

        If a playlist with the given ``uri`` doesn't exist, it returns
        :class:`None`.

        :rtype: list of :class:`mopidy.models.Ref`, or :class:`None`

        .. versionadded:: 1.0
        """
        logger.debug("TidalPlaylistsProvider.get_items(%s)", uri)
        injections = {p.uri: p for p in self.INJECTED_PLAYLISTS.values()}
        if uri in injections:
            return [
                Ref.track(uri=t.uri, name=t.name)
                for t in injections[uri].tracks
            ]
        return [
            t.ref
            for t in lookup_uri(self.backend.session, uri).tracks()
        ]

    def create(self, name: str) -> Playlist:
        """
        Create a new empty playlist with the given name.

        Returns a new playlist with the given name and an URI, or :class:`None`
        on failure.

        *MUST be implemented by subclass.*

        :param name: name of the new playlist
        :type name: string
        :rtype: :class:`mopidy.models.Playlist` or :class:`None`
        """
        logger.debug("TidalPlaylistsProvider.create(%s)", name)
        return Playlist(
            uri=self.NEW_PLAYLIST_URI,
            name=name,
            tracks=[],
            last_modified=0
        )

    def delete(self, uri: str) -> bool:
        """
        Delete playlist identified by the URI.

        Returns :class:`True` if deleted, :class:`False` otherwise.

        *MUST be implemented by subclass.*

        :param uri: URI of the playlist to delete
        :type uri: string
        :rtype: :class:`bool`

        .. versionchanged:: 2.2
            Return type defined.
        """
        logger.error("NotImplemented: TidalPlaylistsProvider.delete(%s)", uri)
        return False

    @cached(TTLCache(maxsize=1, ttl=3), key=lambda _, uri: hash(uri))
    def lookup(self, uri: str) -> Optional[Playlist]:
        """
        Lookup playlist with given URI in both the set of playlists and in any
        other playlist source.

        Returns the playlists or :class:`None` if not found.

        *MUST be implemented by subclass.*

        :param uri: playlist URI
        :type uri: string
        :rtype: :class:`mopidy.models.Playlist` or :class:`None`
        """
        logger.debug("TidalPlaylistsProvider.lookup(%s)", uri)
        injections = {p.uri: p for p in self.INJECTED_PLAYLISTS.values()}
        if uri in injections:
            return injections[uri]
        return lookup_uri(self.backend.session, uri).full

    def refresh(self, *args, **kwargs) -> None:
        """
        Refresh the playlists in :attr:`playlists`.

        *MUST be implemented by subclass.*
        """
        logger.error("NotImplemented: TidalPlaylistsProvider.refresh(%s, %s)", args, kwargs)

    def save(self, playlist: Playlist) -> Optional[Playlist]:
        """
        Save the given playlist.

        The playlist must have an ``uri`` attribute set. To create a new
        playlist with an URI, use :meth:`create`.

        Returns the saved playlist or :class:`None` on failure.

        *MUST be implemented by subclass.*

        :param playlist: the playlist to save
        :type playlist: :class:`mopidy.models.Playlist`
        :rtype: :class:`mopidy.models.Playlist` or :class:`None`
        """
        old_playlist = self.lookup.cache.get(hash(playlist.uri))
        if old_playlist:
            logger.debug("TidalPlaylistsProvider.save: existing %s, %s, %i", playlist.uri, playlist.name, len(playlist.tracks))
            new_tracks = set(t.uri for t in playlist.tracks)
            old_tracks = set(t.uri for t in old_playlist.tracks)
            if URI.from_string(playlist.uri).playlist in ["radio", "mix"]:
                return self._create_track_playlist(new_tracks - old_tracks, playlist)
            self._save_tracks(new_tracks - old_tracks, playlist)
            self._delete_tracks(old_tracks - new_tracks, old_playlist)
        elif playlist.uri == self.NEW_PLAYLIST_URI:
            logger.debug("TidalPlaylistsProvider.save: new %s, %s, %i", playlist.uri, playlist.name, len(playlist.tracks))
            self._create_new_playlist(playlist)
        else:
            logger.error("NotImplemented: TidalPlaylistsProvider.save(%s)", playlist)
        return playlist

    def _create_track_playlist(self, tracks: Iterable[Track], playlist: Playlist) -> Playlist:
        track = lookup_uri(self.backend, next(iter(tracks), playlist.tracks[-1].uri))
        method = URI.from_string(playlist.uri).playlist
        logger.debug(f"Getting {method} for track: %s", track.name)
        playlist = playlist.replace(
            name=f"{method}: {track.name}",
            tracks=[t.full for t in getattr(track, method, lambda: [])()],
        )
        self.INJECTED_PLAYLISTS[method] = playlist
        return playlist

    def _save_tracks(self, tracks, playlist):
        logger.error("NotImplemented: TidalPlaylistsProvider._save_tracks(%s, %s)", tracks, playlist.uri)

    def _delete_tracks(self, tracks, playlist):
        logger.error("NotImplemented: TidalPlaylistsProvider._delete_tracks(%s, %s)", tracks, playlist.uri)

    def _create_new_playlist(self, playlist):
        logger.error("NotImplemented: TidalPlaylistsProvider._create_new_playlist(%s, %s)", playlist.tracks, playlist.name)
