"""Network fetches in parallel threads. Only the fetch runs in the pool: the database work stays in the
caller's thread (a Session is not thread-safe)."""

from collections.abc import Callable, Hashable, Iterable
from concurrent.futures import ThreadPoolExecutor

WORKERS = 8


def fetch_all[K: Hashable, R](
    fetch: Callable[[K], R], keys: Iterable[K], workers: int = WORKERS
) -> dict[K, R | Exception]:
    """`fetch(key)` for every key; a failure is returned as the exception instead of raised."""
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}
    with ThreadPoolExecutor(max_workers=min(workers, len(keys))) as pool:
        futures = {key: pool.submit(fetch, key) for key in keys}
    out: dict[K, R | Exception] = {}
    for key, future in futures.items():
        try:
            out[key] = future.result()
        except Exception as err:  # noqa: BLE001 — the caller decides what a failure means
            out[key] = err
    return out
