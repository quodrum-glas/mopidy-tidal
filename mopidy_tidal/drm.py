from __future__ import annotations

"""DRM playback: mp4decrypt per-segment, local DASH server for GStreamer."""

import logging
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse

import requests

if TYPE_CHECKING:
    from tidalapi.api.stream import StreamInfo

logger = logging.getLogger(__name__)

_NS = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}


def _mp4decrypt(
    data: bytes, kid: str, key: str, init_data: bytes | None = None,
) -> bytes:
    """Decrypt bytes via mp4decrypt."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(data)
        enc = Path(f.name)
    dec = enc.with_suffix(".dec.mp4")
    init_file: Path | None = None
    try:
        cmd = ["mp4decrypt", "--key", f"{kid}:{key}"]
        if init_data:
            init_file = enc.with_suffix(".init.mp4")
            init_file.write_bytes(init_data)
            cmd += ["--fragments-info", str(init_file)]
        cmd += [str(enc), str(dec)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"mp4decrypt failed: {r.stderr}")
        return dec.read_bytes()
    finally:
        enc.unlink(missing_ok=True)
        dec.unlink(missing_ok=True)
        if init_file:
            init_file.unlink(missing_ok=True)


def _strip_mpd_to_single_rep(mpd_xml: str, preferred_codec: str = "flac") -> str:
    """Remove all but the preferred Representation from the MPD.

    Also strips ContentProtection elements so dashdemux doesn't think
    the stream is encrypted.
    """
    root = ET.fromstring(mpd_xml)
    for adapt in root.findall(".//mpd:AdaptationSet", _NS):
        # Remove ContentProtection
        for cp in adapt.findall("mpd:ContentProtection", _NS):
            adapt.remove(cp)

        # Keep only the preferred representation
        reps = adapt.findall("mpd:Representation", _NS)
        best = reps[0]
        for r in reps:
            codecs = (r.get("codecs", "") + r.get("id", "")).lower()
            if preferred_codec in codecs:
                best = r
                break
        for r in reps:
            if r is not best:
                adapt.remove(r)

    ET.register_namespace("", "urn:mpeg:dash:schema:mpd:2011")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


class _DashServer:
    """Minimal HTTP server that resolves request paths to bytes via a callback."""

    def __init__(self, resolver: Callable[[str], bytes | None]) -> None:
        self._resolver = resolver
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                data = server._resolver(path)
                if data is None:
                    self._send(b"Not found", "text/plain", 404)
                else:
                    ct = "application/dash+xml" if path.endswith(".mpd") else "audio/mp4"
                    self._send(data, ct)

            do_HEAD = do_GET

            def _send(self, data: bytes, ct: str, code: int = 200) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    try:
                        self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def log_message(self, *a) -> None:
                pass

        self._http = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._http.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        threading.Thread(
            target=self._http.serve_forever, name="mopidy-tidal-drm-http", daemon=True,
        ).start()

    def shutdown_later(self, seconds: int = 600) -> None:
        def _stop() -> None:
            import time
            time.sleep(seconds)
            self._http.shutdown()

        threading.Thread(target=_stop, name="mopidy-tidal-drm-stop", daemon=True).start()


def decrypt_stream(stream: StreamInfo, keys: list[tuple[str, str]]) -> str:
    """Start a local DASH server serving decrypted segments.

    Returns an http:// URL to the patched MPD. GStreamer's dashdemux requests
    init + segments on demand — seeking and progressive playback work natively.
    """
    if not keys:
        raise RuntimeError(f"No content keys for track {stream.track_id}")

    kid, key_hex = keys[0]
    mpd_xml = stream.get_manifest_data()
    if not mpd_xml:
        raise RuntimeError(f"No MPD manifest for track {stream.track_id}")

    cache: dict[str, bytes] = {}
    lock = threading.Lock()
    init_enc: list[bytes] = []
    init_ready = threading.Event()

    # Build path -> URL map from stream.init_url and stream.urls
    url_map: dict[str, str] = {}
    if stream.init_url:
        url_map[urlparse(stream.init_url).path] = stream.init_url
    for url in stream.urls:
        url_map[urlparse(url).path] = url

    def _prefetch() -> None:
        # Init segment
        if stream.init_url:
            resp = requests.get(stream.init_url)
            resp.raise_for_status()
            init_enc.append(resp.content)
            path = urlparse(stream.init_url).path
            cache[path] = _mp4decrypt(resp.content, kid, key_hex)
        init_ready.set()

        # All media segments (parallel download)
        from concurrent.futures import ThreadPoolExecutor

        def _fetch(item: tuple[str, str]) -> tuple[str, bytes]:
            path, url = item
            r = requests.get(url)
            r.raise_for_status()
            return path, r.content

        seg_items = [(urlparse(u).path, u) for u in stream.urls]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for path, enc in pool.map(_fetch, seg_items):
                dec = _mp4decrypt(enc, kid, key_hex, init_enc[0] if init_enc else None)
                with lock:
                    cache[path] = dec

        logger.info("DRM: cached all %d segments for track %s", len(stream.urls), stream.track_id)

    def _resolve(path: str) -> bytes | None:
        if path == "/manifest.mpd":
            return cache.get("/manifest.mpd")
        init_ready.wait(timeout=15)
        with lock:
            return cache.get(path)

    server = _DashServer(_resolve)

    # Strip MPD to single representation and rewrite origin
    quality = stream.audio_quality or ""
    preferred = "flac" if "LOSSLESS" in quality else ""
    patched = _strip_mpd_to_single_rep(mpd_xml, preferred)
    if stream.urls:
        p = urlparse(stream.urls[0])
        patched = patched.replace(f"{p.scheme}://{p.netloc}", server.base_url)
    cache["/manifest.mpd"] = patched.encode()

    threading.Thread(target=_prefetch, name="mopidy-tidal-drm-init", daemon=True).start()
    server.start()
    server.shutdown_later()

    init_ready.wait(timeout=15)
    url = f"{server.base_url}/manifest.mpd"
    logger.info("DRM: serving track %s at %s", stream.track_id, url)
    return url
