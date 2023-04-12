from __future__ import unicode_literals

import logging
import os
import sys
from itertools import chain

from mopidy import config, ext
from tidalapi import Quality

__version__ = "0.3.2"

# TODO: If you need to log, use loggers named after the current Python module
logger = logging.getLogger(__name__)

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)


class Extension(ext.Extension):

    dist_name = "Mopidy-Tidal"
    ext_name = "tidal"
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), "ext.conf")
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema["client_id"] = config.Secret()
        schema["client_secret"] = config.Secret(optional=True)
        schema["quality"] = config.String(choices=[e.value for e in Quality])
        schema["playlist_cache_refresh_secs"] = config.Integer(
            optional=True,
            choices=chain(range(10, 60, 10), range(60, 600, 60), range(600, 3601, 600))
        )
        schema["search_result_count"] = config.Integer(
            optional=True,
            choices=range(0, 201, 50)
        )
        schema["login_web_port"] = config.Integer(optional=True, choices=range(8000, 9000))
        return schema

    def setup(self, registry):
        from .backend import TidalBackend
        registry.add("backend", TidalBackend)
