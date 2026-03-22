from __future__ import annotations

from functools import partial

from mopidy_tidal.workers import MAX_WORKERS, paginated, sorted_threaded, threaded


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
        a = lambda: "first"
        b = lambda: "second"
        c = lambda: "third"
        results = sorted_threaded(a, b, c)
        assert results == ["first", "second", "third"]


class TestPaginated:
    def test_single_page(self):
        call = lambda limit, offset: list(range(offset, offset + 3))
        pages = list(paginated(call, limit=50))
        assert pages == [[0, 1, 2]]

    def test_total_splits_into_pages(self):
        data = list(range(120))

        def call(limit, offset):
            return data[offset:offset + limit]

        pages = list(paginated(call, limit=50, total=120))
        flat = [item for page in pages for item in page]
        assert flat == data

    def test_total_exact_multiple(self):
        data = list(range(100))

        def call(limit, offset):
            return data[offset:offset + limit]

        pages = list(paginated(call, limit=50, total=100))
        flat = [item for page in pages for item in page]
        assert flat == data
