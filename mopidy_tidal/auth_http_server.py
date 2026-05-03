from __future__ import annotations

import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue
from string import whitespace
from urllib.parse import unquote

from tidalapi import Session

HTML_BODY = """<!DOCTYPE html>
<html>
<head>
<title>TIDAL OAuth Login</title>
</head>
<body>

<h1>KEEP THIS TAB OPEN</h1>
<a href={authurl} target="_blank" rel="noopener noreferrer">Click here to be forwarded to TIDAL Login page</a>
{interactive}

</body>
</html>
""".format

INTERACTIVE_HTML_BODY = """
<p>...then, after login, copy the whole final URL of the page you ended up to.</p>
<p>Probably a "not found" page, nevertheless we need the whole URL as is.</p>
<form method="post">
  <label for="code">Paste here your final URL location:</label>
  <input type="url" id="code" name="code">
  <input type="submit" value="Submit">
</form>
"""


def start_oauth_daemon(
    session: Session,
    port: int,
    on_login: Queue[bool],
) -> HTTPServer:
    login_handler = LoginHandler(session, on_login)
    handler = partial(HTTPHandler, login_handler)
    server = HTTPServer(("", port), handler)
    threading.Thread(
        name="TidalOAuthLogin",
        target=server.serve_forever,
        daemon=True,
    ).start()
    return server


class HTTPHandler(BaseHTTPRequestHandler):
    def __init__(
        self,
        login_handler: LoginHandler,
        *args: object,
        **kwargs: object,
    ) -> None:
        self.login_handler = login_handler
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        interactive = INTERACTIVE_HTML_BODY if self.login_handler.is_pkce else ""
        self.wfile.write(HTML_BODY(authurl=self.login_handler.get_login_url(), interactive=interactive).encode())

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        try:
            form = dict(p.split("=", 1) for p in body.split("&"))
            code_url = unquote(form["code"].strip(whitespace))
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Malformed request")
            raise
        try:
            self.login_handler.set_login_result(code_url)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Success!\nCredentials auto-refresh is on.\nEnjoy your music!")
        except Exception:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Failed to get final key! :(")
            raise


class LoginHandler:
    def __init__(self, session: Session, on_login: Queue[bool]) -> None:
        self._session = session
        self._on_login = on_login
        self.is_pkce: bool = session.is_pkce
        self._login_url: str | None = None

    def _login_oauth(self) -> str:
        login, future = self._session.login_oauth()
        future.add_done_callback(lambda f: self.set_login_result(f.exception()))
        return login.verification_uri_complete

    def _login_pkce(self) -> str:
        return self._session.pkce_login_url()

    def get_login_url(self) -> str:
        if self._login_url is None:
            self._login_url = self._login_pkce() if self.is_pkce else self._login_oauth()
        return self._login_url

    def set_login_result(self, data: str | Exception | None) -> None:
        if self.is_pkce:
            try:
                self._session.complete_pkce_login(data)
            except Exception:
                self._login_url = None
                raise
        self._on_login.put(True)
