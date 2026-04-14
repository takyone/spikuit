"""SpikuitTransaction — synchronous amkb.Transaction wrapping Circuit.transaction().

Scaffolding only. The real implementation (context manager bridging,
``_AbortSignal`` sentinel, mutation delegation) lands in task #14.
See design doc §5.4.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import amkb

    from spikuit_agents.amkb.store import SpikuitStore


class _AbortSignal(BaseException):
    """Adapter-private sentinel that drives ``Circuit.transaction()`` down
    its abort path via ``asynccontextmanager.__aexit__``.

    Never escapes the adapter — :class:`SpikuitTransaction` catches it
    in its own ``__exit__`` so callers only see
    :class:`amkb.AmkbError` subclasses.
    """


class SpikuitTransaction:
    """AMKB Transaction implementation backed by ``Circuit.transaction()``.

    Construct via :meth:`SpikuitStore.begin`. Do not instantiate
    directly.
    """

    def __init__(
        self,
        store: "SpikuitStore",
        *,
        tag: str,
        actor: "amkb.Actor",
    ) -> None:
        self._store = store
        self.tag = tag
        self.actor = actor.id
        self._actor_obj = actor
        self._tx_ctx: Any = None
        self._tx: Any = None
        self.ref: Any = None

    def __enter__(self) -> "SpikuitTransaction":
        raise NotImplementedError("filled in by task #14")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        raise NotImplementedError("filled in by task #14")

    def commit(self) -> "amkb.ChangeSet":
        raise NotImplementedError("filled in by task #14")

    def abort(self) -> None:
        raise NotImplementedError("filled in by task #14")

    # -- Mutations -----------------------------------------------------

    def create(
        self, *, kind: str, layer: str, content: str,
        attrs: dict[str, Any] | None = None,
    ) -> "amkb.NodeRef":
        raise NotImplementedError("filled in by task #14")

    def rewrite(
        self, ref: "amkb.NodeRef", *, content: str, reason: str,
    ) -> "amkb.NodeRef":
        raise NotImplementedError("filled in by task #14")

    def retire(self, ref: "amkb.NodeRef", *, reason: str) -> None:
        raise NotImplementedError("filled in by task #14")

    def merge(
        self,
        refs: list["amkb.NodeRef"],
        *,
        content: str,
        attrs: dict[str, Any] | None = None,
        reason: str,
    ) -> "amkb.NodeRef":
        raise NotImplementedError("filled in by task #14")

    def link(
        self,
        src: "amkb.NodeRef",
        dst: "amkb.NodeRef",
        *,
        rel: str,
        attrs: dict[str, Any] | None = None,
    ) -> "amkb.EdgeRef":
        raise NotImplementedError("filled in by task #14")

    def unlink(self, ref: "amkb.EdgeRef", *, reason: str) -> None:
        raise NotImplementedError("filled in by task #14")

    def get_node(self, ref: "amkb.NodeRef") -> "amkb.Node":
        raise NotImplementedError("filled in by task #14")

    def get_edge(self, ref: "amkb.EdgeRef") -> "amkb.Edge":
        raise NotImplementedError("filled in by task #14")


__all__ = ["SpikuitTransaction"]
