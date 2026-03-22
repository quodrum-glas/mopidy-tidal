from __future__ import annotations

"""Caching decorators for model objects."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from cachetools import LRUCache, TTLCache, cached
from cachetools.keys import hashkey

CACHE_TTL: int = 86400  # 24 hours

_model_cache: LRUCache = LRUCache(maxsize=16_384)
_items_cache: TTLCache = TTLCache(maxsize=4096, ttl=CACHE_TTL)
_futures_cache: TTLCache = TTLCache(maxsize=1024, ttl=CACHE_TTL)

cached_by_uri = cached(
    _model_cache,
    key=lambda *args, uri, **kwargs: hash(uri),
)

cached_items = cached(
    _items_cache,
    key=lambda item, *args, **kwargs: hashkey(item.uri, item.last_modified),
)

cached_future = cached(
    _futures_cache,
    key=lambda *args, uri, **kwargs: hash(uri),
)


def cache_by_uri(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Store the returned model in _model_cache keyed by its URI."""
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        item = fn(*args, **kwargs)
        _model_cache[hash(item.ref.uri)] = item
        return item
    return wrapper


def cache_future(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        item = fn(*args, **kwargs)
        if item:
            _futures_cache[hash(item.ref.uri)] = item
        return item
    return wrapper
