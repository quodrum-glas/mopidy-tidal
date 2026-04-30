from __future__ import annotations

"""DRM playback: stateless decrypting reverse proxy for GStreamer."""

import logging
import threading
from collections import OrderedDict
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

import requests
from mpegdash.parser import MPEGDASHParser
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_full_jitter,
)
from tidalapi.http import TidalRequestsSession
from tidalapi.mp4decrypt import EncryptionParams, decrypt_init, decrypt_segment
from urllib3.exceptions import ResponseError

if TYPE_CHECKING:
    from mpegdash.nodes import MPEGDASH, Representation
    from tidalapi.api.stream import StreamInfo

logger = logging.getLogger(__name__)

_HEADERS_MPD = {"Content-Type": "application/dash+xml", "Cache-Control": "max-age=31536000"}
_HEADERS_SEGMENT = {"Content-Type": "audio/mp4"}


def _seg_urls(rep: Representation) -> tuple[str, set[str]]:
    """Extract (init_url, {media_urls}) from a Representation's SegmentTemplate."""
    st = rep.segment_templates[0]
    start = int(st.start_number)
    count = sum(1 + int(s.r or 0) for s in st.segment_timelines[0].Ss)
    return (
        st.initialization,
        {st.media.replace("$Number$", str(i)) for i in range(start, start + count)},
    )


def _generate_mpd_xml(mpd: MPEGDASH, proxy_prefix: str, selected_rep_ids: set[str]) -> str:
    """Strip ContentProtection, keep selected Representations, proxy its URLs."""
    mpd = MPEGDASHParser.parse(mpd.xml)
    for period in mpd.periods:
        for adapt in period.adaptation_sets:
            adapt.content_protections = None
            adapt.representations = [
                r for r in adapt.representations if r.id in selected_rep_ids
            ]
            for rep in adapt.representations:
                logger.debug(f"Representation served: {rep.id}")
                for seg in rep.segment_templates or []:
                    if seg.initialization is None or seg.media is None:
                        raise ValueError("SegmentTemplate missing 'initialization' or 'media'")
                    seg.initialization = seg.initialization.replace(
                        "https://", proxy_prefix, 1
                    )
                    seg.media = seg.media.replace("https://", proxy_prefix, 1)
    return MPEGDASHParser.get_as_doc(mpd).toxml()


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
        if path.endswith("/manifest.mpd"):
            self._reply(self.drm.mpd_bytes, _HEADERS_MPD)
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
    GStreamer picks the representation; we decrypt whatever it requests.
    """

    def __init__(self, http_timeout: tuple[float, float]) -> None:
        self.http = TidalRequestsSession(
            timeout=http_timeout,
            pool_connections=2,
            pool_maxsize=4,
        )
        self.mpd_bytes: bytes = b""
        # init_url → (media_urls_set, cached_params) — ordered by bandwidth
        self._reprs: OrderedDict[str, tuple[set[str], EncryptionParams | None]] = OrderedDict()
        self.key_hex: str = ""
        self._stop = threading.Event()
        handler = partial(_Handler, self)
        super().__init__(("127.0.0.1", 0), handler)
        host, port = self.server_address
        self.base_url = f"http://{host}:{port}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_full_jitter(max=2),
        retry=retry_if_exception_type((requests.exceptions.RequestException, ResponseError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def fetch(self, url: str) -> bytes:
        logger.debug("fetch %s", url)
        r = self.http.get(url)
        r.raise_for_status()
        return r.content

    def _get_params(self, init_url: str) -> EncryptionParams:
        urls, params = self._reprs[init_url]
        if not params:
            raw = self.fetch(init_url)
            params = decrypt_init(raw, self.key_hex)
            self._reprs[init_url] = (urls, params)
        return params

    def decrypt(self, path: str) -> bytes:
        upstream = f"https:/{path}"

        for init_url, (media_urls, _) in self._reprs.items():
            params = self._get_params(init_url)
            if upstream == init_url:
                return params.clean_init
            if upstream in media_urls:
                raw = self.fetch(upstream)
                return decrypt_segment(raw, params)

        raise RuntimeError(f"Unknown URL: {upstream}")

    def reset(self, mpd: MPEGDASH, key_hex: str) -> str:
        """Configure for a new track. Returns the local MPD URL."""
        self._reprs = OrderedDict()
        repr_ids = set()
        # Adaptive representations not handled by gstreamer as may need to switch codec mid-track play
        # We will enforce the highest quality available as per user configuration
        for r in mpd.periods[0].adaptation_sets[0].representations[:1]:
            init_url, media_urls = _seg_urls(r)
            self._reprs[init_url] = (media_urls, None)
            repr_ids.add(r.id)
        self.mpd_bytes = _generate_mpd_xml(mpd, f"{self.base_url}/", repr_ids).encode()
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
    """Return a local URL to a cleaned MPD proxied through the DRM server."""
    if not keys:
        raise RuntimeError(f"No content keys for track {stream.track_id}")
    if not stream.mpd:
        raise RuntimeError(f"No MPD manifest for track {stream.track_id}")

    _, key_hex = keys[0]
    return server.reset(stream.mpd, key_hex)
