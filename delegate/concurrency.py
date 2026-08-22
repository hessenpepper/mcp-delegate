"""Caps how many delegations (single-shot or agentic) run at once.

MCP tool functions defined as plain `def` are already offloaded to worker
threads by the server (see anyio.to_thread.run_sync), so concurrent calls
run in parallel without any extra plumbing. This just adds a ceiling so a
large fan-out of delegations doesn't overwhelm a local model server or blow
through a paid API's rate limits.
"""

import os
import threading
from contextlib import contextmanager

_MAX_CONCURRENT_DELEGATIONS = int(os.environ.get("DELEGATE_MAX_CONCURRENCY", "4"))
_semaphore = threading.Semaphore(_MAX_CONCURRENT_DELEGATIONS)


@contextmanager
def limit_concurrency():
    _semaphore.acquire()
    try:
        yield
    finally:
        _semaphore.release()
