import datetime
import json
import logging
from os.path import basename

from tidalapi import Session


logger = logging.getLogger(__name__)


class PersistentSession(Session):

    def __init__(self, *args, login_pkce, authentication_local_storage, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_pkce = login_pkce
        self._authentication_local_storage = authentication_local_storage

    def load_oauth_session_from_file(self):
        with open(self._authentication_local_storage, 'r') as f:
            data = json.load(f)
        data["expiry_time"] = datetime.datetime.fromisoformat(data["expiry_time"])
        self.load_oauth_session(**data)
        logger.info("Session loaded from %s - Expires at %s", basename(self._authentication_local_storage), self.expiry_time.isoformat())

    def save_oauth_session_to_file(self):
        with open(self._authentication_local_storage, 'w') as f:
            json.dump({
                "token_type": self.token_type,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expiry_time": self.expiry_time.isoformat(),
            }, f)
        logger.info("Session saved to %s - Expires at %s", basename(self._authentication_local_storage), self.expiry_time.isoformat())

    def token_refresh(self, *args, **kwargs):
        logger.info("Authentication expired at %s ...Refreshing", self.expiry_time.isoformat())
        refreshed = super().token_refresh(*args, **kwargs)
        if refreshed:
            logger.info("Authentication renewed until %s", self.expiry_time.isoformat())
            self.save_oauth_session_to_file()
        else:
            logger.info("Authentication failed to renew")
        return refreshed


    def process_auth_token(self, *args, **kwargs):
        super().process_auth_token(*args, **kwargs)
        self.save_oauth_session_to_file()
