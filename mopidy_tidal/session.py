from __future__ import annotations

"""Session factory for mopidy-tidal.

Creates a tidalapi.Session configured from mopidy config.
No subclass — the new tidalapi handles persistence and refresh natively.
"""

import logging
from pathlib import Path

from tidalapi import Session

logger = logging.getLogger(__name__)


def create_session(
    *,
    client_id: str,
    client_secret: str = "",
    quality: str = "HIGH",
    token_file: str | Path | None = None,
) -> Session:
    """Create a tidalapi Session from mopidy config values.

    If token_file exists, loads credentials and the session is ready to use.
    Otherwise returns a deferred session — call login methods on it.
    """
    if token_file:
        try:
            return Session(
                token_file=token_file,
                client_id=client_id,
                client_secret=client_secret,
                quality=quality,
            )
        except Exception:
            logger.warning("Could not load session from %s", token_file, exc_info=True)

    return Session(
        client_id=client_id,
        client_secret=client_secret,
        quality=quality,
    )
