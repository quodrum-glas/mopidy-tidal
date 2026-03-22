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
    login_result: Queue[Exception | None],
) -> None:
    handler = partial(HTTPHandler, session, login_result)
    threading.Thread(
        name="TidalOAuthLogin",
        target=HTTPServer(("", port), handler).serve_forever,
        daemon=True,
    ).start()


class HTTPHandler(BaseHTTPRequestHandler):

    def __init__(
        self,
        session: Session,
        login_result_holder: Queue[Exception | None],
        *args: object,
        **kwargs: object,
    ) -> None:
        self.login_handler = LoginHandler(session, login_result_holder)
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        interactive = INTERACTIVE_HTML_BODY if self.login_handler.is_pkce else ""
        self.wfile.write(
            HTML_BODY(authurl=self.login_handler.get_login_url(), interactive=interactive).encode()
        )

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
    def __init__(self, session: Session, login_result_holder: Queue[Exception | None]) -> None:
        self._session = session
        self._login_result_holder = login_result_holder
        self.is_pkce: bool = session.is_pkce

    def _login_oauth(self) -> str:
        login, future = self._session.login_oauth()
        future.add_done_callback(lambda f: self.set_login_result(f.exception()))
        return login.verification_uri_complete

    def _login_pkce(self) -> str:
        return self._session.pkce_login_url()

    def get_login_url(self) -> str:
        return self._login_pkce() if self.is_pkce else self._login_oauth()

    def set_login_result(self, data: str | Exception | None) -> None:
        if self.is_pkce:
            try:
                self._session.complete_pkce_login(data)
                data = None
            except Exception as e:
                data = e
        self._login_result_holder.put(data)
