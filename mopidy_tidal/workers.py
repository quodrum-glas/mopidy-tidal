from __future__ import annotations

"""Threaded and paginated execution helpers."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        yield from sorted_threaded(*(
            partial(call, limit=limit, offset=limit * idx)
            for idx in range(pages)
        ))
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
