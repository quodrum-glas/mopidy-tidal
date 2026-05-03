from __future__ import annotations

import logging
import os
from importlib.metadata import version as _dist_version
from itertools import chain

from mopidy import config, ext
from tidalapi import Quality

logger = logging.getLogger(__name__)


class Extension(ext.Extension):
    dist_name = "Mopidy-Tidal"
    ext_name = "tidal"
    version = _dist_version(dist_name)

    def get_default_config(self) -> str:
        conf_file = os.path.join(os.path.dirname(__file__), "ext.conf")
        return config.read(conf_file)

    def get_config_schema(self) -> config.ConfigSchema:
        schema = super().get_config_schema()
        schema["client_id"] = config.Secret()
        schema["client_secret"] = config.Secret(optional=True)
        schema["widevine_cdm_path"] = config.Path(optional=True)
        schema["quality"] = config.String(choices=[e.value for e in Quality])
        schema["fetch_album_covers"] = config.Boolean(optional=True)
        schema["playlist_cache_refresh_secs"] = config.Integer(
            optional=True,
            choices=chain(range(10, 60, 10), range(60, 600, 60), range(600, 3601, 600)),
        )
        schema["pagination_max_results"] = config.Integer(
            optional=True,
            choices=range(20, 101, 20),
        )
        schema["login_web_port"] = config.Integer(optional=True, minimum=8000, maximum=8999)
        schema["http_timeout"] = config.Pair(
            optional=True,
            separator=",",
            subtypes=(config.Float(), config.Float()),
        )
        return schema

    def setup(self, registry: ext.Registry) -> None:
        from .backend import TidalBackend

        registry.add("backend", TidalBackend)
