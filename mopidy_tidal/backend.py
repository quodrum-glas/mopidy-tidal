from __future__ import annotations

import logging
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from mopidy import backend
from pykka import ThreadingActor

from mopidy_tidal import Extension, library, playback, playlists
from mopidy_tidal.auth_http_server import start_oauth_daemon
from mopidy_tidal.session import create_session

logger = logging.getLogger(__name__)


class TidalBackend(ThreadingActor, backend.Backend):
    EXT: str = Extension.ext_name

    def __init__(self, config: dict, audio: object) -> None:
        super().__init__()
        self.session = None
        self._config = config
        self.playback = playback.TidalPlaybackProvider(audio=audio, backend=self)
        self.library = library.TidalLibraryProvider(backend=self)
        self.playlists = playlists.TidalPlaylistsProvider(
            backend=self,
            playlist_cache_ttl=config[self.EXT].get("playlist_cache_refresh_secs"),
        )
        self.uri_schemes = [self.EXT]
        self.quality: str = self._ext("quality")
        self.data_dir = Extension.get_data_dir(config)
        self.cache_dir = Extension.get_cache_dir(config)

    def _ext(self, key: str) -> Any:
        return self._config[self.EXT].get(key)

    def on_start(self) -> None:
        client_id: str = self._ext("client_id")
        client_secret: str = self._ext("client_secret")
        token_file: Path = self.data_dir / f"tidal.oauth.{client_id}.json"

        logger.info("Connecting to TIDAL... quality=%s", self.quality)

        self.session = create_session(
            client_id=client_id,
            client_secret=client_secret,
            quality=self.quality,
            token_file=token_file,
        )

        if not self.session.check_login():
            self._new_login()

        if self.session.check_login():
            self.session.save_session_to_file(token_file)
            logger.info(
                "TIDAL Login OK: user=%s country=%s",
                self.session.user_id,
                self.session.country_code,
            )
        else:
            logger.error("TIDAL Login failed")

    def _new_login(self) -> None:
        port: int = self._ext("login_web_port")
        result: Queue[Exception | None] = Queue(maxsize=1)
        start_oauth_daemon(self.session, port, result)
        logger.info("No credentials. Visit http://localhost:%s to authenticate", port)
        try:
            exc = result.get(timeout=300)
            if exc:
                raise exc
        except Empty:
            raise TimeoutError("Login timed out")
