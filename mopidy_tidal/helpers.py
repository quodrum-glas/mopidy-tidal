from __future__ import annotations

"""Small helpers: timestamp conversion, error swallowing."""

import datetime
import logging
import socket
import time
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


def backoff_on_error(seconds: float = 5.0):
    """Decorator: on exception, return None and suppress further calls for `seconds`."""

    def decorator(fn):
        fail_until: list[float] = [0.0]

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if time.monotonic() < fail_until[0]:
                logger.debug("Skipping %s (cooling down)", fn.__name__)
                return None
            try:
                result = fn(*args, **kwargs)
                fail_until[0] = 0.0
                return result
            except Exception as e:
                logger.warning("%s failed, backing off %.0fs", fn.__name__, seconds)
                logger.exception(e)
                fail_until[0] = time.monotonic() + seconds
                return None

        return wrapper

    return decorator


def to_timestamp(dt: str | datetime.datetime | float | None) -> int:
    if not dt:
        return 0
    if isinstance(dt, str):
        if dt.lower() == "today":
            return int(datetime.datetime.combine(datetime.datetime.now().date(), datetime.time.min).timestamp())
        # Handle 'Z' suffix (UTC timezone indicator)
        if dt.endswith("Z"):
            dt = dt[:-1] + "+00:00"
        # 3.10 fromisoformat needs +00:00, not +0000
        elif len(dt) >= 5 and dt[-5] in "+-" and dt[-3] != ":":
            dt = dt[:-2] + ":" + dt[-2:]
        dt = datetime.datetime.fromisoformat(dt)
    if isinstance(dt, datetime.datetime):
        return int(dt.timestamp())
    return int(dt)


def try_or_none(call: object, *args: Any, **kwargs: Any) -> Any:
    try:
        return call(*args, **kwargs)
    except Exception:
        return None


def return_none(*args: Any, **kwargs: Any) -> None:
    return None


def login_required(fallback):
    """Decorator: return *fallback* immediately if provider.backend.logged_in is False."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(provider, *args, **kwargs):
            if not provider.backend.logged_in:
                return fallback(provider.backend) if callable(fallback) else fallback
            return fn(provider, *args, **kwargs)

        return wrapper

    return decorator


from tenacity import retry, stop_after_delay, wait_fixed


@retry(stop=stop_after_delay(60), wait=wait_fixed(1))
def local_ip() -> str:
    """Return the local IP. Retries for up to 60s, then raises."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    finally:
        s.close()
