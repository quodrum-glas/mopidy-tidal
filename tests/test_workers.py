from __future__ import annotations

import pytest

from mopidy_tidal.workers import MAX_WORKERS, BatchCollector, paginated, sorted_threaded, threaded


class TestThreaded:
    def test_returns_all_results(self):
        results = list(threaded(lambda: 1, lambda: 2, lambda: 3))
        assert sorted(results) == [1, 2, 3]

    def test_empty(self):
        assert list(threaded()) == []

    def test_max_workers_capped(self):
        assert MAX_WORKERS == 4


class TestSortedThreaded:
    def test_preserves_input_order(self):
        def a():
            return "first"

        def b():
            return "second"

        def c():
            return "third"

        results = sorted_threaded(a, b, c)
        assert results == ["first", "second", "third"]


class TestPaginated:
    def test_single_page(self):
        def call(limit, offset):
            return list(range(offset, offset + 3))

        pages = list(paginated(call, limit=50))
        assert pages == [[0, 1, 2]]

    def test_total_splits_into_pages(self):
        data = list(range(120))

        def call(limit, offset):
            return data[offset : offset + limit]

        pages = list(paginated(call, limit=50, total=120))
        flat = [item for page in pages for item in page]
        assert flat == data

    def test_total_exact_multiple(self):
        data = list(range(100))

        def call(limit, offset):
            return data[offset : offset + limit]

        pages = list(paginated(call, limit=50, total=100))
        flat = [item for page in pages for item in page]
        assert flat == data


class TestBatchCollector:
    def test_flush_on_max_size(self):
        def flush_fn(keys):
            return {k: k.upper() for k in keys}

        bc = BatchCollector(flush_fn=flush_fn, timeout=10, max_size=2)
        f1 = bc.submit("a")
        f2 = bc.submit("b")  # triggers flush (max_size=2)
        assert f1.result(timeout=2) == "A"
        assert f2.result(timeout=2) == "B"

    def test_flush_on_timeout(self):
        def flush_fn(keys):
            return {k: len(k) for k in keys}

        bc = BatchCollector(flush_fn=flush_fn, timeout=0.1, max_size=100)
        f = bc.submit("hello")
        assert f.result(timeout=2) == 5

    def test_flush_fn_exception_propagates(self):
        def flush_fn(keys):
            raise RuntimeError("batch failed")

        bc = BatchCollector(flush_fn=flush_fn, timeout=0.1, max_size=100)
        f = bc.submit("x")
        with pytest.raises(RuntimeError, match="batch failed"):
            f.result(timeout=2)

    def test_missing_key_raises_key_error(self):
        def flush_fn(keys):
            return {}  # returns nothing

        bc = BatchCollector(flush_fn=flush_fn, timeout=0.1, max_size=100)
        f = bc.submit("missing")
        with pytest.raises(KeyError):
            f.result(timeout=2)
