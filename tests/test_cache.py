from __future__ import annotations

from types import SimpleNamespace

import pytest

from mopidy_tidal.cache import (
    _futures_cache,
    _items_cache,
    _model_cache,
    cache_by_uri,
    cache_by_uri_if,
    cache_future,
    cached_by_uri,
    cached_future,
    cached_items,
)


def _ref(uri: str) -> SimpleNamespace:
    return SimpleNamespace(uri=uri)


def _model(uri: str, **extra) -> SimpleNamespace:
    return SimpleNamespace(ref=_ref(uri), **extra)


@pytest.fixture(autouse=True)
def _clear_caches():
    _model_cache.clear()
    _items_cache.clear()
    _futures_cache.clear()
    yield
    _model_cache.clear()
    _items_cache.clear()
    _futures_cache.clear()


# -- cache_by_uri ---------------------------------------------------------

class TestCacheByUri:
    def test_stores_in_model_cache(self):
        @cache_by_uri
        def build(api):
            return _model("tidal:track:1")

        result = build(None)
        assert _model_cache[hash("tidal:track:1")] is result

    def test_returns_result(self):
        @cache_by_uri
        def build(api):
            return _model("tidal:track:2")

        assert build(None).ref.uri == "tidal:track:2"

    def test_overwrites_on_repeat(self):
        calls = 0

        @cache_by_uri
        def build(api):
            nonlocal calls
            calls += 1
            return _model("tidal:track:3", n=calls)

        build(None)
        build(None)
        assert calls == 2
        assert _model_cache[hash("tidal:track:3")].n == 2


# -- cached_by_uri --------------------------------------------------------

class TestCachedByUri:
    def test_caches_by_uri_kwarg(self):
        calls = 0

        @cached_by_uri
        def fetch(session, *, uri):
            nonlocal calls
            calls += 1
            return _model(uri)

        fetch(None, uri="tidal:album:10")
        fetch(None, uri="tidal:album:10")
        assert calls == 1

    def test_different_uris_cached_separately(self):
        calls = 0

        @cached_by_uri
        def fetch(session, *, uri):
            nonlocal calls
            calls += 1
            return _model(uri)

        fetch(None, uri="tidal:album:1")
        fetch(None, uri="tidal:album:2")
        assert calls == 2


# -- cached_items ---------------------------------------------------------

class TestCachedItems:
    def test_caches_by_uri_and_last_modified(self):
        calls = 0

        @cached_items
        def get_tracks(item):
            nonlocal calls
            calls += 1
            return ["t1", "t2"]

        item = SimpleNamespace(uri="tidal:playlist:5", last_modified=100)
        get_tracks(item)
        get_tracks(item)
        assert calls == 1

    def test_invalidates_on_last_modified_change(self):
        calls = 0

        @cached_items
        def get_tracks(item):
            nonlocal calls
            calls += 1
            return [f"v{calls}"]

        item = SimpleNamespace(uri="tidal:playlist:5", last_modified=100)
        get_tracks(item)
        item.last_modified = 200
        get_tracks(item)
        assert calls == 2


# -- cache_future / cached_future -----------------------------------------

class TestCacheFuture:
    def test_stores_in_futures_cache(self):
        @cache_future
        def resolve(api):
            return _model("tidal:future:1")

        result = resolve(None)
        assert _futures_cache[hash("tidal:future:1")] is result

    def test_skips_none(self):
        @cache_future
        def resolve(api):
            return None

        resolve(None)
        assert len(_futures_cache) == 0


class TestCachedFuture:
    def test_caches_by_uri_kwarg(self):
        calls = 0

        @cached_future
        def fetch(session, *, uri):
            nonlocal calls
            calls += 1
            return _model(uri)

        fetch(None, uri="tidal:future:9")
        fetch(None, uri="tidal:future:9")
        assert calls == 1


# -- cache isolation ------------------------------------------------------

class TestCacheIsolation:
    def test_model_and_futures_are_separate(self):
        @cache_by_uri
        def build(api):
            return _model("tidal:track:99")

        @cache_future
        def resolve(api):
            return _model("tidal:track:99")

        m = build(None)
        f = resolve(None)
        assert _model_cache[hash("tidal:track:99")] is m
        assert _futures_cache[hash("tidal:track:99")] is f
        assert m is not f


# -- cache_by_uri_if ------------------------------------------------------

class TestCacheByUriIf:
    def test_caches_when_check_passes(self):
        @cache_by_uri_if(lambda item: item.ok)
        def build(api):
            m = _model("tidal:track:50")
            m.ok = True
            return m

        result = build(None)
        assert _model_cache[hash("tidal:track:50")] is result

    def test_skips_cache_when_check_fails(self):
        @cache_by_uri_if(lambda item: item.ok)
        def build(api):
            m = _model("tidal:track:51")
            m.ok = False
            return m

        build(None)
        assert hash("tidal:track:51") not in _model_cache

    def test_still_returns_result_when_not_cached(self):
        @cache_by_uri_if(lambda item: False)
        def build(api):
            return _model("tidal:track:52")

        result = build(None)
        assert result.ref.uri == "tidal:track:52"
