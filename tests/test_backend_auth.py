from __future__ import annotations

from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from mopidy_tidal.auth_http_server import LoginHandler, start_oauth_daemon
from mopidy_tidal.session import create_session

_SESSION_KW = dict(
    client_id="cid",
    client_secret="",
    quality="HIGH",
    fetch_album_covers=False,
    http_timeout=(3.05, 1.5),
)


# ── create_session ───────────────────────────────────────────────────────


class TestCreateSession:
    def test_loads_from_token_file(self, tmp_path):
        token = tmp_path / "tidal.json"
        token.write_text(
            '{"token_type":"Bearer","access_token":"tok",'
            '"refresh_token":"ref","expiry_time":"2099-01-01T00:00:00",'
            '"is_pkce":true}'
        )
        s = create_session(**_SESSION_KW, token_file=token)
        assert s.auth is not None
        assert s.auth.access_token == "tok"

    def test_falls_back_to_deferred_on_missing_file(self, tmp_path):
        token = tmp_path / "missing.json"
        s = create_session(**_SESSION_KW, token_file=token)
        assert s.auth is None

    def test_falls_back_to_deferred_on_corrupt_file(self, tmp_path):
        token = tmp_path / "bad.json"
        token.write_text("not json")
        s = create_session(**_SESSION_KW, token_file=token)
        assert s.auth is None

    def test_deferred_without_token_file(self):
        s = create_session(**_SESSION_KW)
        assert s.auth is None

    def test_passes_quality(self, tmp_path):
        token = tmp_path / "tidal.json"
        token.write_text(
            '{"token_type":"Bearer","access_token":"tok",'
            '"refresh_token":"ref","expiry_time":"2099-01-01T00:00:00"}'
        )
        s = create_session(
            **{**_SESSION_KW, "quality": "LOSSLESS"}, token_file=token,
        )
        assert s.config.quality == "LOSSLESS"

    def test_passes_client_secret(self, tmp_path):
        token = tmp_path / "tidal.json"
        token.write_text(
            '{"token_type":"Bearer","access_token":"tok",'
            '"refresh_token":"ref","expiry_time":"2099-01-01T00:00:00",'
            '"is_pkce":false}'
        )
        s = create_session(
            **{**_SESSION_KW, "client_secret": "sec"}, token_file=token,
        )
        assert s.auth.client_secret == "sec"


# ── LoginHandler ─────────────────────────────────────────────────────────


class TestLoginHandlerPkce:
    @pytest.fixture()
    def session(self):
        s = MagicMock()
        s.is_pkce = True
        s.pkce_login_url.return_value = "https://login.tidal.com/authorize?..."
        return s

    @pytest.fixture()
    def queue(self):
        return Queue(maxsize=1)

    @pytest.fixture()
    def handler(self, session, queue):
        return LoginHandler(session, queue)

    def test_is_pkce(self, handler):
        assert handler.is_pkce is True

    def test_get_login_url_calls_pkce(self, handler, session):
        url = handler.get_login_url()
        session.pkce_login_url.assert_called_once()
        assert url == "https://login.tidal.com/authorize?..."

    def test_set_login_result_calls_complete_pkce_login(self, handler, session, queue):
        handler.set_login_result("https://tidal.com/android/login/auth?code=abc")
        session.complete_pkce_login.assert_called_once_with(
            "https://tidal.com/android/login/auth?code=abc"
        )
        assert queue.get_nowait() is True

    def test_set_login_result_reraises_on_failure(self, handler, session, queue):
        session.complete_pkce_login.side_effect = ValueError("bad code")
        with pytest.raises(ValueError, match="bad code"):
            handler.set_login_result("https://bad-url")
        assert queue.empty()


class TestLoginHandlerDeviceCode:
    @pytest.fixture()
    def session(self):
        s = MagicMock()
        s.is_pkce = False
        link = MagicMock()
        link.verification_uri_complete = "https://link.tidal.com/ABCDE"
        future = MagicMock()
        s.login_oauth.return_value = (link, future)
        return s

    @pytest.fixture()
    def queue(self):
        return Queue(maxsize=1)

    @pytest.fixture()
    def handler(self, session, queue):
        return LoginHandler(session, queue)

    def test_is_not_pkce(self, handler):
        assert handler.is_pkce is False

    def test_get_login_url_calls_login_oauth(self, handler, session):
        url = handler.get_login_url()
        session.login_oauth.assert_called_once()
        assert url == "https://link.tidal.com/ABCDE"

    def test_get_login_url_registers_callback(self, handler, session):
        handler.get_login_url()
        _, future = session.login_oauth.return_value
        future.add_done_callback.assert_called_once()

    def test_device_code_callback_on_success(self, handler, session, queue):
        handler.get_login_url()
        _, future = session.login_oauth.return_value
        callback = future.add_done_callback.call_args[0][0]
        mock_future = MagicMock()
        mock_future.exception.return_value = None
        callback(mock_future)
        assert queue.get_nowait() is True

    def test_device_code_callback_on_failure(self, handler, session, queue):
        handler.get_login_url()
        _, future = session.login_oauth.return_value
        callback = future.add_done_callback.call_args[0][0]
        mock_future = MagicMock()
        mock_future.exception.return_value = TimeoutError("expired")
        callback(mock_future)
        assert queue.get_nowait() is True


# ── start_oauth_daemon ───────────────────────────────────────────────────


class TestStartOauthDaemon:
    @patch("mopidy_tidal.auth_http_server.HTTPServer")
    @patch("mopidy_tidal.auth_http_server.threading.Thread")
    def test_starts_daemon_thread(self, mock_thread_cls, mock_server_cls):
        session = MagicMock()
        q = Queue()
        start_oauth_daemon(session, 8989, q)
        mock_server_cls.assert_called_once()
        assert mock_server_cls.call_args[0][0] == ("", 8989)
        mock_thread_cls.assert_called_once()
        call_kw = mock_thread_cls.call_args[1]
        assert call_kw["daemon"] is True
        assert call_kw["name"] == "TidalOAuthLogin"
        mock_thread_cls.return_value.start.assert_called_once()


# ── TidalBackend.on_start ────────────────────────────────────────────────


class TestBackendOnStart:
    def _make_backend(self, tmp_path):
        """Create a TidalBackend with mocked super().__init__ and providers."""
        from mopidy_tidal.backend import TidalBackend

        config = {
            "tidal": {
                "client_id": "test_id",
                "client_secret": "",
                "quality": "HIGH",
                "fetch_album_covers": False,
                "playlist_cache_refresh_secs": 60,
                "login_web_port": 8989,
                "widevine_cdm_path": None,
                "http_timeout": (3.05, 1.5),
                "pagination_max_results": 40,
            },
            "core": {"data_dir": str(tmp_path)},
        }

        with patch.object(TidalBackend, "__init__", lambda self, *a, **kw: None):
            b = TidalBackend.__new__(TidalBackend)

        b._config = config
        b.session = None
        b.logged_in = False
        b.EXT = "tidal"
        b.data_dir = tmp_path
        b.cache_dir = tmp_path
        b.quality = "HIGH"
        b.http_timeout = (3.05, 1.5)
        b.drm_server = None
        return b

    @patch("mopidy_tidal.backend.local_ip", return_value="127.0.0.1")
    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    def test_existing_session_skips_login(self, mock_create, mock_data_dir, mock_ip, tmp_path):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = True
        session.user_id = 123
        session.country_code = "IE"
        mock_create.return_value = session

        with patch.object(b, "_start_drm_proxy"):
            b.on_start()

        session.save_session_to_file.assert_called_once()
        assert b.session is session
        assert b.logged_in is True

    @patch("mopidy_tidal.backend.local_ip", return_value="127.0.0.1")
    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    @patch("mopidy_tidal.backend.start_oauth_daemon")
    def test_new_login_triggered_when_check_fails(
        self, mock_daemon, mock_create, mock_data_dir, mock_ip, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = False
        session.user_id = 456
        session.country_code = "US"
        mock_create.return_value = session

        b.on_start()

        mock_daemon.assert_called_once()
        # Login is now non-blocking, so save is not called immediately
        assert b.logged_in is False

    @patch("mopidy_tidal.backend.local_ip", return_value="127.0.0.1")
    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    def test_token_file_path_includes_client_id(
        self, mock_create, mock_data_dir, mock_ip, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = True
        session.user_id = 1
        session.country_code = "IE"
        mock_create.return_value = session

        with patch.object(b, "_start_drm_proxy"):
            b.on_start()

        call_kw = mock_create.call_args[1]
        assert "test_id" in str(call_kw["token_file"])
        assert call_kw["client_id"] == "test_id"
        assert call_kw["quality"] == "HIGH"
