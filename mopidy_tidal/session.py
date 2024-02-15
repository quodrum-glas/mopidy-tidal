import datetime
import json
import logging

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
        logger.info(f"Session Loaded. Expires at {self.expiry_time.isoformat()}")

    def save_oauth_session_to_file(self):
        with open(self._authentication_local_storage, 'w') as f:
            json.dump({
                "token_type": self.token_type,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expiry_time": self.expiry_time.isoformat(),
            }, f)
        logger.info(f"Session Saved. Expires at {self.expiry_time.isoformat()}")

    def token_refresh(self, *args, **kwargs):
        logger.info(f"Authentication expired at {self.expiry_time.isoformat()} ...Refreshing")
        refreshed = super().token_refresh(*args, **kwargs)
        if refreshed:
            logger.info(f"Authentication renewed until {self.expiry_time.isoformat()}")
            self.save_oauth_session_to_file()
        else:
            logger.info(f"Authentication failed to renew.")
        return refreshed


    def process_auth_token(self, *args, **kwargs):
        super().process_auth_token(*args, **kwargs)
        self.save_oauth_session_to_file()
