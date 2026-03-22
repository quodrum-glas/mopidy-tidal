from __future__ import annotations

from queue import Empty, Queue
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from mopidy_tidal.auth_http_server import LoginHandler, start_oauth_daemon
from mopidy_tidal.session import create_session


# ── create_session ───────────────────────────────────────────────────────


class TestCreateSession:
    def test_loads_from_token_file(self, tmp_path):
        token = tmp_path / "tidal.json"
        token.write_text(
            '{"token_type":"Bearer","access_token":"tok",'
            '"refresh_token":"ref","expiry_time":"2099-01-01T00:00:00",'
            '"is_pkce":true}'
        )
        s = create_session(client_id="cid", token_file=token)
        assert s.auth is not None
        assert s.auth.access_token == "tok"

    def test_falls_back_to_deferred_on_missing_file(self, tmp_path):
        token = tmp_path / "missing.json"
        s = create_session(client_id="cid", token_file=token)
        assert s.auth is None
        assert s.client is None

    def test_falls_back_to_deferred_on_corrupt_file(self, tmp_path):
        token = tmp_path / "bad.json"
        token.write_text("not json")
        s = create_session(client_id="cid", token_file=token)
        assert s.auth is None

    def test_deferred_without_token_file(self):
        s = create_session(client_id="cid")
        assert s.auth is None
        assert s.client is None

    def test_passes_quality(self, tmp_path):
        token = tmp_path / "tidal.json"
        token.write_text(
            '{"token_type":"Bearer","access_token":"tok",'
            '"refresh_token":"ref","expiry_time":"2099-01-01T00:00:00"}'
        )
        s = create_session(client_id="cid", quality="LOSSLESS", token_file=token)
        assert s.config.quality == "LOSSLESS"

    def test_passes_client_secret(self, tmp_path):
        token = tmp_path / "tidal.json"
        token.write_text(
            '{"token_type":"Bearer","access_token":"tok",'
            '"refresh_token":"ref","expiry_time":"2099-01-01T00:00:00",'
            '"is_pkce":false}'
        )
        s = create_session(client_id="cid", client_secret="sec", token_file=token)
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
        assert queue.get_nowait() is None

    def test_set_login_result_captures_exception(self, handler, session, queue):
        session.complete_pkce_login.side_effect = ValueError("bad code")
        handler.set_login_result("https://bad-url")
        exc = queue.get_nowait()
        assert isinstance(exc, ValueError)
        assert "bad code" in str(exc)


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

    def test_set_login_result_none_puts_none(self, handler, queue):
        handler.set_login_result(None)
        assert queue.get_nowait() is None

    def test_set_login_result_exception_puts_exception(self, handler, queue):
        exc = RuntimeError("poll failed")
        handler.set_login_result(exc)
        assert queue.get_nowait() is exc

    def test_device_code_callback_on_success(self, handler, session, queue):
        handler.get_login_url()
        _, future = session.login_oauth.return_value
        callback = future.add_done_callback.call_args[0][0]
        # Simulate successful future: exception() returns None
        mock_future = MagicMock()
        mock_future.exception.return_value = None
        callback(mock_future)
        assert queue.get_nowait() is None

    def test_device_code_callback_on_failure(self, handler, session, queue):
        handler.get_login_url()
        _, future = session.login_oauth.return_value
        callback = future.add_done_callback.call_args[0][0]
        mock_future = MagicMock()
        mock_future.exception.return_value = TimeoutError("expired")
        callback(mock_future)
        exc = queue.get_nowait()
        assert isinstance(exc, TimeoutError)


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
                "playlist_cache_refresh_secs": 60,
                "login_web_port": 8989,
            },
            "core": {"data_dir": str(tmp_path)},
        }

        with patch.object(TidalBackend, "__init__", lambda self, *a, **kw: None):
            b = TidalBackend.__new__(TidalBackend)

        b._config = config
        b.session = None
        b.EXT = "tidal"
        return b

    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    def test_existing_session_skips_login(self, mock_create, mock_data_dir, tmp_path):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = True
        session.user_id = 123
        session.country_code = "IE"
        mock_create.return_value = session

        b.on_start()

        session.save_session_to_file.assert_called_once()
        assert b.session is session

    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    @patch("mopidy_tidal.backend.start_oauth_daemon")
    def test_new_login_triggered_when_check_fails(
        self, mock_daemon, mock_create, mock_data_dir, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        # First check_login fails, second (after login) succeeds
        session.check_login.side_effect = [False, True]
        session.user_id = 456
        session.country_code = "US"
        mock_create.return_value = session

        def fake_daemon(sess, port, result_queue):
            result_queue.put(None)  # simulate successful login

        mock_daemon.side_effect = fake_daemon

        b.on_start()

        mock_daemon.assert_called_once()
        session.save_session_to_file.assert_called_once()

    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    @patch("mopidy_tidal.backend.start_oauth_daemon")
    def test_login_failure_logged(
        self, mock_daemon, mock_create, mock_data_dir, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = False
        mock_create.return_value = session

        def fake_daemon(sess, port, result_queue):
            result_queue.put(None)

        mock_daemon.side_effect = fake_daemon

        b.on_start()

        session.save_session_to_file.assert_not_called()

    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    @patch("mopidy_tidal.backend.start_oauth_daemon")
    def test_login_exception_propagates(
        self, mock_daemon, mock_create, mock_data_dir, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = False
        mock_create.return_value = session

        def fake_daemon(sess, port, result_queue):
            result_queue.put(RuntimeError("auth failed"))

        mock_daemon.side_effect = fake_daemon

        with pytest.raises(RuntimeError, match="auth failed"):
            b.on_start()

    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    @patch("mopidy_tidal.backend.start_oauth_daemon")
    def test_login_timeout(
        self, mock_daemon, mock_create, mock_data_dir, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = False
        mock_create.return_value = session

        # Don't put anything in the queue — simulate timeout
        mock_daemon.side_effect = lambda s, p, q: None

        with patch("mopidy_tidal.backend.TidalBackend._new_login") as mock_login:
            mock_login.side_effect = TimeoutError("Login timed out")
            with pytest.raises(TimeoutError):
                b.on_start()

    @patch("mopidy_tidal.backend.Extension.get_data_dir")
    @patch("mopidy_tidal.backend.create_session")
    def test_token_file_path_includes_client_id(
        self, mock_create, mock_data_dir, tmp_path
    ):
        mock_data_dir.return_value = tmp_path
        b = self._make_backend(tmp_path)

        session = MagicMock()
        session.check_login.return_value = True
        session.user_id = 1
        session.country_code = "IE"
        mock_create.return_value = session

        b.on_start()

        call_kw = mock_create.call_args[1]
        assert "test_id" in str(call_kw["token_file"])
        assert call_kw["client_id"] == "test_id"
        assert call_kw["quality"] == "HIGH"
