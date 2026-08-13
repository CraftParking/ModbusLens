import threading
import time


class SharedReadCache:
    """A tiny (space, start, end) -> values cache shared between Tag Monitoring's poll
    worker (a background QThread) and Trend's own poll timer (GUI thread), so the exact
    same register range configured in both doesn't cost two wire round-trips every cycle.

    Deliberately exact-range-only -- no partial-overlap/subrange matching. Tag Monitoring
    builds merged multi-tag blocks (see read_merge.py) and Trend reads one pen at a time;
    only a byte-for-byte identical (space, start, end) is guaranteed to mean the same
    request, and fuzzy-matching a subrange out of a differently-shaped block risks
    silently serving the wrong slice.

    A short TTL (default 500ms) bounds staleness: two pollers with similar cadences that
    happen to land within the same short window share one wire read, but a poller with a
    much longer interval always falls outside the window by the time its own tick comes
    around, so it never serves data older than its own cadence would have been anyway.
    Thread-safe: TagPollWorker calls this from a background thread while Trend calls it
    from the GUI thread, both potentially at once."""

    def __init__(self, ttl_seconds=0.5):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._entries = {}  # (space, start, end) -> (monotonic_timestamp, values)

    def get(self, space, start, end):
        key = (space, start, end)
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        timestamp, values = entry
        if time.monotonic() - timestamp > self._ttl:
            return None
        return list(values) if isinstance(values, list) else values

    def put(self, space, start, end, values):
        if values is None:
            return
        key = (space, start, end)
        with self._lock:
            self._entries[key] = (time.monotonic(), values)
