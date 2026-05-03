from __future__ import annotations

import logging
import threading
from pathlib import Path
from queue import Queue
from typing import Any

from mopidy import backend
from pykka import ThreadingActor

from mopidy_tidal import Extension, library, playback, playlists
from mopidy_tidal.auth_http_server import start_oauth_daemon
from mopidy_tidal.drm import DrmServer
from mopidy_tidal.helpers import filtered_logging, local_ip
from mopidy_tidal.session import create_session

logger = logging.getLogger(__name__)


class TidalBackend(ThreadingActor, backend.Backend):
    EXT: str = Extension.ext_name

    def __init__(self, config: dict, audio: object) -> None:
        super().__init__()
        self.session = None
        self.logged_in = False
        self._config = config
        self.drm_server: DrmServer | None = None
        self.playback = playback.TidalPlaybackProvider(audio=audio, backend=self)
        self.library = library.TidalLibraryProvider(backend=self)
        self.playlists = playlists.TidalPlaylistsProvider(
            backend=self, playlist_cache_ttl=self._ext("playlist_cache_refresh_secs")
        )
        self.uri_schemes = [self.EXT]
        self.quality: str = self._ext("quality")
        self.http_timeout: tuple[float, float] = self._ext("http_timeout")
        self.pagination_max_results = self._ext("pagination_max_results")
        self.data_dir = Extension.get_data_dir(config)
        self.cache_dir = Extension.get_cache_dir(config)

    def _ext(self, key: str) -> Any:
        return self._config[self.EXT].get(key)

    def on_start(self) -> None:
        client_id: str = self._ext("client_id")
        client_secret: str = self._ext("client_secret")
        token_file: Path = self.data_dir / f"tidal.oauth.{client_id}.json"
        widevine_cdm_path = self._ext("widevine_cdm_path")
        fetch_album_covers: bool = self._ext("fetch_album_covers")

        ip = local_ip()

        logger.info("Connecting to TIDAL... quality=%s", self.quality)

        self.session = create_session(
            client_id=client_id,
            client_secret=client_secret,
            quality=self.quality,
            token_file=token_file,
            widevine_cdm_path=widevine_cdm_path,
            fetch_album_covers=fetch_album_covers,
            http_timeout=self.http_timeout,
        )

        self.logged_in = self.session.check_login()
        if self.logged_in:
            self.session.save_session_to_file(token_file)
            logger.info("TIDAL Login OK: user=%s country=%s", self.session.user_id, self.session.country_code)
            self._start_drm_proxy()
        else:
            self._new_login(token_file, ip)

    def _start_drm_proxy(self) -> None:
        self.drm_server = DrmServer(http_timeout=self.http_timeout)
        self.drm_server.start()

    def _new_login(self, token_file: Path, ip: str) -> None:
        port: int = self._ext("login_web_port")
        self._login_url = f"http://{ip}:{port}"
        on_login: Queue[bool] = Queue(maxsize=1)
        server = start_oauth_daemon(self.session, port, on_login)
        logger.info("No credentials. Visit %s to authenticate", self._login_url)
        threading.Thread(
            name="TidalOAuthWait", target=self._wait_for_login, args=(token_file, on_login, server), daemon=True
        ).start()

    def _wait_for_login(self, token_file: Path, on_login: Queue[bool], server) -> None:
        on_login.get()
        server.shutdown()
        self.logged_in = True
        self.session.save_session_to_file(token_file)
        self._login_url = None
        logger.info("TIDAL Login OK: user=%s country=%s", self.session.user_id, self.session.country_code)

    def on_stop(self) -> None:
        if self.drm_server:
            self.drm_server.shutdown()
