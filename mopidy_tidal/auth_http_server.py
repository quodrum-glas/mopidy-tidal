import threading
from functools import partial
from string import whitespace

from mopidy_tidal.session import PersistentSession

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse

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
<p>Probably a "Not Found" ("Ooops!" ?) page, nevertheless we need the whole URL as is.</p>
<form method="post">
  <label for="code">Paste here your final URL location:</label>
  <input type="url" id="code" name="code">
  <input type="submit" value="Submit">
</form>
"""

def start_oauth_deamon(session, port, login_result_holder):
    handler = partial(HTTPHandler, session, login_result_holder)
    http_server = HTTPServer(('', port), handler)
    daemon = threading.Thread(
        name="TidalOAuthLogin",
        target=http_server.serve_forever
    )
    daemon.daemon = True  # Set as a daemon, so it will be killed once the main thread is dead.
    daemon.start()
    return http_server.shutdown


class HTTPHandler(BaseHTTPRequestHandler, object):

    def __init__(self, session: PersistentSession, login_result_holder, *args, **kwargs):
        self.login_handler = LoginHandler(session, login_result_holder)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        url = urlparse(self.path)
        self.send_response(200)
        self.end_headers()
        if url.path == '/' and url.query == '' and url.params == '':
            interactive = INTERACTIVE_HTML_BODY if self.login_handler.is_pkce else ''
            self.wfile.write(HTML_BODY(authurl=self.login_handler.get_login_url(), interactive=interactive).encode())

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length"), 0)
        body = self.rfile.read(content_length).decode()
        try:
            form = {k: v for k, v in (p.split("=", 1) for p in body.split("&"))}
            code_url = unquote(form['code'].strip(whitespace))
        except:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Malformed request")
            raise
        else:
            try:
                self.login_handler.set_login_result(code_url)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Success!\nCredentials auto-refresh is on.\nEnjoy your music!")
            except:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Failed to get final key! :(")
                raise


class LoginHandler:
    def __init__(self, session: PersistentSession, login_result_holder):
        self._session = session
        self._login_result_holder = login_result_holder
        self.is_pkce = session.is_pkce

    def _login_oauth(self):
        login, future = self._session.login_oauth()
        future.add_done_callback(lambda f: self.set_login_result(f.exception()))
        return login.verification_uri_complete

    def _login_pkce(self):
        return self._session.pkce_login_url()

    def get_login_url(self):
        if self.is_pkce:
            return self._login_pkce()
        else:
            return self._login_oauth()

    def set_login_result(self, data):
        if self.is_pkce:
            try:
                self._session.process_auth_token(self._session.pkce_get_auth_token(data))
                data = None
            except Exception as e:
                data = e
        self._login_result_holder.put(data)