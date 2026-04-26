from __future__ import annotations

"""DRM playback: stateless decrypting reverse proxy for GStreamer."""

import logging
import threading
import xml.etree.ElementTree as ET
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_full_jitter,
)
from urllib3.exceptions import ResponseError

from tidalapi.http import TTLRequestsSessionManager
from tidalapi.mp4decrypt import EncryptionParams, decrypt_init, decrypt_segment

if TYPE_CHECKING:
    from tidalapi.api.stream import StreamInfo

logger = logging.getLogger(__name__)

_NS = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}
_HEADERS_MPD = {"Content-Type": "application/dash+xml", "Cache-Control": "max-age=31536000"}
_HEADERS_SEGMENT = {"Content-Type": "audio/mp4"}


def _rewrite_mpd(mpd_xml: str, proxy_prefix: str, representation_id: str) -> tuple[str, str]:
    """Strip DRM, keep one Representation, replace https:// with proxy_prefix.

    Returns (patched_mpd_xml, init_path).
    """
    root = ET.fromstring(mpd_xml)
    init_path = ""
    for adapt in root.findall(".//mpd:AdaptationSet", _NS):
        for cp in adapt.findall("mpd:ContentProtection", _NS):
            adapt.remove(cp)
        reps = adapt.findall("mpd:Representation", _NS)
        best = next((r for r in reps if r.get("id") == representation_id), None)
        if best is None:
            raise ValueError(
                f"Representation '{representation_id}' not found "
                f"(available: {[r.get('id') for r in reps]})"
            )
        for r in reps:
            if r is not best:
                adapt.remove(r)
            else:
                for seg in r.findall("mpd:SegmentTemplate", _NS):
                    for attr in ("initialization", "media"):
                        val = seg.get(attr)
                        if val is None:
                            raise ValueError(f"SegmentTemplate missing '{attr}'")
                        seg.set(attr, val.replace("https://", proxy_prefix, 1))
                        if attr == "initialization":
                            init_path = val
    ET.register_namespace("", _NS["mpd"])
    return ET.tostring(root, encoding="unicode", xml_declaration=True), init_path


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, server: DrmServer, *args: object, **kwargs: object) -> None:
        self.drm = server
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        path = self.path
        if self.drm.mpd and path.endswith("/manifest.mpd"):
            self._reply(self.drm.mpd, _HEADERS_MPD)
            return
        try:
            data = self.drm.decrypt(path)
        except (requests.exceptions.RequestException, ResponseError):
            logger.warning("%s -> 503", path.rsplit("/", 1)[-1])
            self._reply(b"Service unavailable", code=503, hdrs={"Retry-After": "2"})
            return
        except Exception:
            logger.exception("%s -> 502", path.rsplit("/", 1)[-1])
            self._reply(b"Bad gateway", code=502)
            return
        self._reply(data, _HEADERS_SEGMENT)

    do_HEAD = do_GET

    def _reply(
        self, data: bytes, hdrs: dict[str, str] | None = None, code: int = 200,
    ) -> None:
        self.send_response(code)
        for k, v in (hdrs or {"Content-Type": "text/plain"}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, *a) -> None:
        pass


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class DrmServer(HTTPServer):
    """Decrypting reverse proxy server.

    URL path mirrors the upstream CDN path. key_hex is stored on the server.
    On GET: reconstruct https:/{path}, fetch, decrypt, return.
    """

    def __init__(self, http_timeout: tuple[float, float]) -> None:
        self.http = TTLRequestsSessionManager(
            timeout=http_timeout,
            pool_connections=2,
            pool_maxsize=4,
        )
        self.mpd: bytes = b""
        self.init_params: EncryptionParams | None = None
        self.key_hex: str = ""
        self.init_path: str = ""
        self._stop = threading.Event()
        handler = partial(_Handler, self)
        super().__init__(("127.0.0.1", 0), handler)
        host, port = self.server_address
        self.base_url = f"http://{host}:{port}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_full_jitter(max=2),
        retry=retry_if_exception_type((requests.exceptions.RequestException, ResponseError)),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    def fetch(self, url: str) -> bytes:
        logger.debug("fetch %s", url)
        r = self.http.get(url)
        r.raise_for_status()
        return r.content

    def decrypt(self, path: str) -> bytes:
        upstream = f"https:/{path}"
        if upstream == self.init_path:
            if not self.init_params:
                raw = self.fetch(upstream)
                self.init_params = decrypt_init(raw, self.key_hex)
            return self.init_params.clean_init

        raw = self.fetch(upstream)
        return decrypt_segment(raw, self.init_params)

    def reset(self, mpd_xml: str, key_hex: str, representation_id: str) -> str:
        """Configure for a new track. Returns the local MPD URL."""
        prefix = f"{self.base_url}/"
        patched, self.init_path = _rewrite_mpd(mpd_xml, prefix, representation_id)
        self.mpd = patched.encode()
        self.init_params = None
        self.key_hex = key_hex
        return f"{self.base_url}/manifest.mpd"

    def start(self) -> None:
        threading.Thread(
            target=self._serve, name="TidalDrmProxy", daemon=True,
        ).start()
        logger.debug("proxy on %s", self.base_url)

    def _serve(self) -> None:
        self.timeout = 0.5
        while not self._stop.is_set():
            self.handle_request()
        self.server_close()

    def shutdown(self) -> None:
        self.http.close()
        self._stop.set()


def decrypt_stream(
    stream: StreamInfo,
    keys: list[tuple[str, str]],
    server: DrmServer,
) -> str:
    """Return a local URL to a patched MPD proxied through the DRM server."""
    if not keys:
        raise RuntimeError(f"No content keys for track {stream.track_id}")
    if not stream.representation_id:
        raise RuntimeError(f"No representation ID for track {stream.track_id}")
    mpd_xml = stream.get_manifest_data()
    if not mpd_xml:
        raise RuntimeError(f"No MPD manifest for track {stream.track_id}")

    _, key_hex = keys[0]
    return server.reset(mpd_xml, key_hex, stream.representation_id)
