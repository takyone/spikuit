"""SpikuitStore — synchronous amkb.Store backed by spikuit_core.Circuit.

Scaffolding only. Method bodies are filled in by task #13. See design
doc §5.2 / §5.3 for the target shape.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from spikuit_agents.amkb._bridge import AsyncBridge

if TYPE_CHECKING:
    import amkb
    from amkb.filters import Filter
    from spikuit_core import Circuit


class SpikuitStore:
    """AMKB Store implementation over a single :class:`Circuit`.

    Use :meth:`SpikuitStore.open` to construct; it takes ownership of
    ``Circuit.connect()``/``close()``. The direct constructor is for
    callers who already drive the Circuit lifecycle externally.
    """

    def __init__(self, circuit: "Circuit") -> None:
        self._circuit = circuit
        self._bridge = AsyncBridge()
        self._owns_connection = False

    @classmethod
    def open(cls, circuit: "Circuit") -> "SpikuitStore":
        store = cls(circuit)
        store._bridge.run(circuit.connect())
        store._owns_connection = True
        return store

    def close(self) -> None:
        if self._owns_connection and not self._bridge.closed:
            self._bridge.run(self._circuit.close())
        self._bridge.close()

    # -- Session entry -------------------------------------------------

    def begin(
        self, *, tag: str, actor: "amkb.Actor",
    ) -> "amkb.Transaction":
        raise NotImplementedError("filled in by task #13")

    # -- Read-only queries ---------------------------------------------

    def get_node(self, ref: "amkb.NodeRef") -> "amkb.Node":
        raise NotImplementedError("filled in by task #13")

    def get_edge(self, ref: "amkb.EdgeRef") -> "amkb.Edge":
        raise NotImplementedError("filled in by task #13")

    def find_by_attr(
        self,
        attributes: dict[str, Any],
        *,
        kind: str | None = None,
        layer: str | None = None,
        include_retired: bool = False,
        limit: int = 100,
    ) -> list["amkb.NodeRef"]:
        raise NotImplementedError("filled in by task #13")

    def neighbors(
        self,
        ref: "amkb.NodeRef",
        *,
        rel: str | list[str] | None = None,
        direction: str = "out",
        depth: int = 1,
        include_retired: bool = False,
        limit: int = 100,
    ) -> list["amkb.NodeRef"]:
        raise NotImplementedError("filled in by task #13")

    def retrieve(
        self,
        intent: str,
        *,
        k: int = 10,
        layer: str | list[str] | None = None,
        filters: "Filter | None" = None,
    ) -> "list[amkb.RetrievalHit]":
        raise NotImplementedError("filled in by task #13")

    # -- History -------------------------------------------------------

    def history(
        self,
        *,
        since: Any = None,
        until: Any = None,
        actor: Any = None,
        tag: str | None = None,
        limit: int = 100,
    ) -> "list[amkb.ChangeSetRef]":
        raise NotImplementedError("filled in by task #13")

    def get_changeset(self, ref: "amkb.ChangeSetRef") -> "amkb.ChangeSet":
        raise NotImplementedError("filled in by task #13")

    def diff(self, from_ts: Any, to_ts: Any) -> "list[amkb.Event]":
        raise NotImplementedError("filled in by task #13")

    def revert(
        self, target: Any, *, reason: str, actor: "amkb.Actor",
    ) -> "amkb.ChangeSet":
        # L3 only — v0.7.1 does not advertise supports_merge_revert.
        from amkb.errors import EConstraint

        raise EConstraint(
            "Spikuit v0.7.1 does not support revert "
            "(supports_merge_revert=False)."
        )

    # -- Events --------------------------------------------------------

    def events(
        self, *, since: Any = None, follow: bool = False,
    ) -> "Iterator[amkb.Event]":
        raise NotImplementedError("filled in by task #13")


__all__ = ["SpikuitStore"]
