from __future__ import unicode_literals

import logging
import os
from queue import Queue, Empty

from mopidy import backend
from pykka import ThreadingActor
from tidalapi import Config, Quality

from mopidy_tidal import Extension, context, library, playback, playlists
from mopidy_tidal.auth_http_server import start_oauth_deamon
from mopidy_tidal.session import PersistentSession
from mopidy_tidal.helpers import get_ip

logger = logging.getLogger(__name__)

OAUTH_JSON = "tidal.oauth.{}.json".format
MAX_LOGIN_WAIT_MINS = 5


class TidalBackend(ThreadingActor, backend.Backend):
    EXT = Extension.ext_name

    def __init__(self, config, audio):
        context.set_config(config[self.EXT])
        super().__init__()
        self.session = None
        self._config = config
        self.playback = playback.TidalPlaybackProvider(audio=audio, backend=self)
        self.library = library.TidalLibraryProvider(backend=self)
        self.playlists = playlists.TidalPlaylistsProvider(
            backend=self,
            playlist_cache_ttl=self.get_config("playlist_cache_refresh_secs")
        )
        self.uri_schemes = [self.EXT]

    def get_config(self, item):
        return self._config[self.EXT].get(item)

    def get_dir(self, folder):
        method = getattr(Extension, f"get_{folder}_dir", None)
        if not method:
            raise ValueError(f"Not a valid folder: {folder}")
        return method(self._config)

    def on_start(self):
        client_id = self.get_config("client_id")
        client_secret = self.get_config("client_secret")
        config = Config(quality=Quality(self.get_config("quality")))
        is_hires_quality = config.quality == Quality.hi_res_lossless.value
        login_pkce = is_hires_quality or self.get_config("login_pkce")
        if client_id:
            if login_pkce:
                config.client_id_pkce = client_id
                config.client_secret_pkce = client_secret
            else:
                config.client_id = client_id
                config.client_secret = client_secret
        client_id_in_use = config.client_id_pkce if login_pkce else config.client_id
        oauth_file_location = os.path.join(self.get_dir("data"), OAUTH_JSON(client_id_in_use))
        self.session = PersistentSession(config, login_pkce=login_pkce, authentication_local_storage=oauth_file_location)
        logger.info("%s connecting to TIDAL. Requested Quality: %s", client_id_in_use, config.quality)
        if is_hires_quality:
            logger.info("Enabling TIDAL HI-RES")
            self.session.client_enable_hires()
        self.connect()

    def connect(self):
        success = False
        try:
            self.session.load_oauth_session_from_file()
            if self.session.check_login():
                logger.info("TIDAL Login OK")
                success = True
            else:
                logger.info("TIDAL Login KO")
                raise PermissionError("Saved session failed to authenticate")
        except (FileNotFoundError, PermissionError, ) as e:
            logger.info(e)
            try:
                self.new_login()
                success = True
            except TimeoutError as e:
                logger.error(e)
            except Exception as e:
                logger.exception(e)
        if not success:
            raise RuntimeError("Failed connection to TIDAL Service")
        subscription = self.session.request.basic_request('GET', f'users/{self.session.user.id}/subscription').json()
        logger.info("Connected to TIDAL. HighestSoundQuality: %s", subscription.get("highestSoundQuality", "UNKNOWN"))

    def new_login(self):
        login_web_port = self.get_config("login_web_port")
        login_result_holder = Queue(maxsize=1)
        terminate = start_oauth_deamon(self.session, login_web_port, login_result_holder)
        logger.info("Please visit http://%s:%i to authenticate", get_ip(), login_web_port)
        try:
            exception = login_result_holder.get(timeout=MAX_LOGIN_WAIT_MINS * 60)
            if exception:
                raise exception
        except Empty:
            raise TimeoutError("Login Timeout")
        terminate()
