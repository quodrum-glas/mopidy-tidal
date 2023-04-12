import threading
from functools import partial
from string import whitespace

from mopidy_tidal.session import PersistentSession, NonLimitedInputDeviceLogin

try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
    from urllib import unquote
except ImportError:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import unquote

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

def start_oauth_deamon(session, port):
    handler = partial(HTTPHandler, session)
    daemon = threading.Thread(
        name="TidalOAuthLogin",
        target=HTTPServer(('', port), handler).serve_forever
    )
    daemon.daemon = True  # Set as a daemon so it will be killed once the main thread is dead.
    daemon.start()


class HTTPHandler(BaseHTTPRequestHandler, object):

    def __init__(self, session: PersistentSession, *args, **kwargs):
        self.login_handler = LoginHandler(session)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.login_handler.login1()
        self.send_response(200)
        self.end_headers()
        interactive = INTERACTIVE_HTML_BODY if self.login_handler.login2 else ''
        self.wfile.write(HTML_BODY(authurl=self.login_handler.login_url, interactive=interactive).encode())

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
                self.login_handler.login2(code_url)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Success!\nCredentials auto-refresh is on.\nEnjoy your music!")
            except:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Failed to get final key! :(")
                raise


class LoginHandler:
    login_url = None
    login1 = None
    login2 = None
    def __init__(self, session: PersistentSession):
        if session.config.client_id:
            response_handler = partial(self.__setattr__, 'login_url')
            if session.config.client_secret:
                self.login1 = partial(session.login_oauth_simple, response_handler)
            else:
                alt_login = NonLimitedInputDeviceLogin(session)
                self.login1 = partial(alt_login.login_oauth_simple, response_handler)
                self.login2 = alt_login.login_oauth_simple_auth_code
        else:
            raise ValueError("At least client_id must be set")