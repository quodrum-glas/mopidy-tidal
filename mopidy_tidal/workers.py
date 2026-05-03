from __future__ import annotations

"""Threaded, paginated, and batched execution helpers."""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from functools import partial
from typing import Any

TIDAL_PAGE_SIZE: int = 50


def paginated(
    call: Callable[..., list],
    limit: int = TIDAL_PAGE_SIZE,
    total: int | None = None,
) -> Iterator[list]:
    if total:
        pages = (total // limit) + min(1, total % limit)
        yield from sorted_threaded(*(partial(call, limit=limit, offset=limit * idx) for idx in range(pages)))
    else:
        idx = 0
        while True:
            results = call(limit=limit, offset=limit * idx)
            yield results
            if len(results) < limit:
                break
            idx += 1


MAX_WORKERS: int = 4


def _threaded(
    *args: Callable[[], Any],
    max_workers: int = MAX_WORKERS,
) -> Iterator[tuple[Callable, Any]]:
    count = len(args)
    if not count:
        return
    with ThreadPoolExecutor(
        max_workers=min(max_workers, count),
        thread_name_prefix="mopidy-tidal-split-",
    ) as executor:
        futures = {executor.submit(call): call for call in args}
        for future in as_completed(futures):
            yield futures[future], future.result()


def threaded(*args: Callable[[], Any], max_workers: int = MAX_WORKERS) -> Iterator[Any]:
    for _, result in _threaded(*args, max_workers=max_workers):
        yield result


def sorted_threaded(*args: Callable[[], Any], **kwargs: Any) -> list[Any]:
    results = dict(_threaded(*args, **kwargs))
    return [results[call] for call in args]


# -- batch collector ------------------------------------------------------


class BatchCollector:
    """Collect items from concurrent threads, flush as a batch.

    Each :meth:`submit` call returns a :class:`~concurrent.futures.Future`.
    When *timeout* expires or *max_size* items accumulate, *flush_fn* is
    called with the full list of keys.  It must return a ``{key: result}``
    dict.  Each waiting Future is resolved from that dict.

    Usage::

        collector = BatchCollector(flush_fn=my_batch_fetch, timeout=0.8)
        future = collector.submit("key1")   # from thread 1
        future = collector.submit("key2")   # from thread 2
        result = future.result()             # blocks until flush
    """

    def __init__(
        self,
        flush_fn: Callable[[list], dict],
        timeout: float = 0.8,
        max_size: int = 50,
    ) -> None:
        self._flush_fn = flush_fn
        self._timeout = timeout
        self._max_size = max_size
        self._lock = threading.Lock()
        self._pending: list[tuple[str, Future]] = []
        self._timer: threading.Timer | None = None

    def submit(self, key: str) -> Future:
        """Add a key to the current batch. Returns a Future for the result."""
        future: Future = Future()
        with self._lock:
            self._pending.append((key, future))
            if len(self._pending) >= self._max_size:
                self._schedule_flush(immediate=True)
            elif self._timer is None:
                self._schedule_flush()
        return future

    def _schedule_flush(self, immediate: bool = False) -> None:
        """Must be called with self._lock held."""
        if self._timer is not None:
            self._timer.cancel()
        if immediate:
            self._timer = None
            threading.Thread(target=self._flush, daemon=True).start()
        else:
            self._timer = threading.Timer(self._timeout, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            batch = self._pending[:]
            self._pending.clear()
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        if not batch:
            return

        keys = [key for key, _ in batch]
        try:
            results = self._flush_fn(keys)
        except Exception as exc:
            for _, future in batch:
                future.set_exception(exc)
            return

        for key, future in batch:
            result = results.get(key)
            if result is not None:
                future.set_result(result)
            else:
                future.set_exception(KeyError(f"Not found in batch: {key}"))
