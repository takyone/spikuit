"""Private sync/async bridge used by the AMKB adapter.

The AMKB SDK Protocol surface is synchronous (see ``amkb.store``
module docstring). :class:`spikuit_core.Circuit` is fully async
(aiosqlite). Each :class:`SpikuitStore` owns a dedicated
``asyncio`` event loop on which Circuit coroutines are driven via
``run_until_complete``.

v0.7.1 ships this bridge only. Once ``amkb-sdk`` grows an
``AsyncStore`` Protocol, a ``SpikuitAsyncStore`` will be added and
this module will become a thin shim.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncBridge:
    """Owned asyncio event loop + run_until_complete helper.

    Not re-entrant. Callers inside a running event loop must not
    invoke bridge methods — use ``loop.run_in_executor`` to hop
    threads first. See design doc §5.2 for the rationale.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._closed = False

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        if self._closed:
            raise RuntimeError("AsyncBridge is closed")
        return self._loop.run_until_complete(coro)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._loop.close()
        finally:
            self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed
