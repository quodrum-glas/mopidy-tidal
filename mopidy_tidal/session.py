import base64
import datetime
import hashlib
import json
import logging
import os
from urllib.parse import urlencode, urljoin, parse_qs, urlsplit

import requests
from tidalapi import Session


logger = logging.getLogger(__name__)


class PersistentSession(Session):

    def __init__(self, *args, authentication_local_storage, **kwargs):
        super().__init__(*args, **kwargs)
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


    def login_oauth_simple(self, *args, **kwargs):
        super().login_oauth_simple(*args, **kwargs)
        self.save_oauth_session_to_file()


class NonLimitedInputDeviceLogin:
    _redirect_uri = "https://tidal.com/android/login/auth"  # or tidal://login/auth
    _oauth_authorize_url = "https://login.tidal.com/authorize"
    _oauth_token_url = "https://auth.tidal.com/v1/oauth2/token"

    def __init__(self, session: PersistentSession):
        self.session = session
        self.code_verifier = None

    def login_oauth_simple(self, result_handler):
        # https://tools.ietf.org/html/rfc7636#appendix-B
        code_verifier = base64.urlsafe_b64encode(os.urandom(32))[:-1]
        self.code_verifier = code_verifier.decode("ascii")
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier).digest())[:-1]
        qs = urlencode(
            {
                "response_type": "code",
                "redirect_uri": self._redirect_uri,
                "client_id": self.session.config.client_id,
                "appMode": "android",
                "code_challenge": code_challenge.decode("ascii"),
                "code_challenge_method": "S256",
                "restrict_signup": "true",
            }
        )
        authorization_url = urljoin(self._oauth_authorize_url, "?" + qs)
        result_handler(authorization_url)

    def login_oauth_simple_auth_code(self, auth_url):
        code = parse_qs(urlsplit(auth_url).query)["code"][0]
        resp = requests.post(
            self._oauth_token_url,
            data={
                "code": code,
                "client_id": self.session.config.client_id,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
                "scope": "r_usr w_usr w_sub",
                "code_verifier": self.code_verifier,
            },
        )
        data = resp.json()
        if resp.status_code != 200:
            raise PermissionError(data["error"], data["error_description"])

        self.session.load_oauth_session(
            token_type=data["token_type"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expiry_time=datetime.datetime.utcnow() + datetime.timedelta(seconds=data.get("expires_in", 0)),
        )
