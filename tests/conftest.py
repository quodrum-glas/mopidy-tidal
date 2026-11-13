from __future__ import annotations

"""Test fixtures."""

import pytest

from mopidy_tidal.tidal import cache


@pytest.fixture(autouse=True)
def _clear_tidal_caches():
    """Isolate tests: the tidal/ caches are module-level singletons."""
    cache.clear()
    yield
    cache.clear()
