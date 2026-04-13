"""Persistent background asyncio loop for sync→async bridging.

The `amkb.Store` Protocol is synchronous, but `spikuit_core.Circuit` is
async. We run a single daemon loop on a worker thread and submit
coroutines via `run_coroutine_threadsafe`, which keeps a live
`aiosqlite` connection usable across adapter calls — the alternative
(`asyncio.run` per call) would reopen the DB on every operation.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


class BackgroundLoop:
    """A daemon-threaded asyncio loop with a sync `run` entry point."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_forever, name="spikuit-amkb-loop", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Submit `coro` to the background loop and block for its result."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    def close(self) -> None:
        if not self._loop.is_running():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
        self._loop.close()
