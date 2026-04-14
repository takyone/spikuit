"""SpikuitStore — synchronous ``amkb.Store`` over :class:`spikuit_core.Circuit`.

Implements the read-side and session-entry surface described in design
doc §5.3. Every async Circuit call is driven through an owned
:class:`AsyncBridge` event loop; every Spikuit exception is translated
at the boundary via :func:`spikuit_agents.amkb.errors.boundary`.

Mutations (the ``begin`` → :class:`SpikuitTransaction` path) are
fleshed out by task #14 — this module leaves ``begin`` as the only
NotImplementedError and documents the wiring there.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from amkb.errors import EConstraint, EEdgeNotFound, ENodeNotFound
from amkb.filters import evaluate as filter_evaluate
from amkb.refs import (
    ActorId,
    ChangeSetRef,
    EdgeRef,
    NodeRef,
    Timestamp,
    TransactionRef,
)
from amkb.store import Direction, RetrievalHit
from amkb.types import (
    KIND_CONCEPT,
    KIND_SOURCE,
    LAYER_CONCEPT,
    LAYER_SOURCE,
    ChangeSet,
    Edge,
    Event,
    Node,
)

from spikuit_core.models import Synapse, SynapseType

from spikuit_agents.amkb._bridge import AsyncBridge
from spikuit_agents.amkb._events import translate_event_rows
from spikuit_agents.amkb.errors import boundary
from spikuit_agents.amkb.mapping import (
    datetime_to_timestamp,
    edge_ref_for_synapse,
    junction_edge,
    neuron_node_ref,
    neuron_to_node,
    source_node_ref,
    source_to_node,
)

if TYPE_CHECKING:
    import amkb
    from amkb.filters import Filter
    from spikuit_core import Circuit


__all__ = ["SpikuitStore"]


def _timestamp_to_iso(ts: Timestamp | int | None) -> str | None:
    """Convert an AMKB Timestamp (µs since epoch) to an ISO-8601 string."""
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts) / 1_000_000, tz=timezone.utc).isoformat()


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
        # Wired up by task #14.
        from spikuit_agents.amkb.transaction import SpikuitTransaction

        return SpikuitTransaction(self, tag=tag, actor=actor)

    # -- Read-only queries ---------------------------------------------

    def get_node(self, ref: "amkb.NodeRef") -> "amkb.Node":
        """Resolve a Node ref (live or retired) — see design doc §5.3 / §5.5."""
        with boundary():
            return self._bridge.run(self._get_node_async(ref))

    def get_edge(self, ref: "amkb.EdgeRef") -> "amkb.Edge":
        """Resolve an Edge ref (live or retired) — see design doc §5.3 / §5.5."""
        with boundary():
            return self._bridge.run(self._get_edge_async(ref))

    def find_by_attr(
        self,
        attributes: dict[str, Any],
        *,
        kind: str | None = None,
        layer: str | None = None,
        include_retired: bool = False,
        limit: int = 100,
    ) -> list["amkb.NodeRef"]:
        """Equality lookup over AMKB attrs (L4a). See design doc §5.3."""
        with boundary():
            return self._bridge.run(
                self._find_by_attr_async(
                    attributes,
                    kind=kind,
                    layer=layer,
                    include_retired=include_retired,
                    limit=limit,
                )
            )

    def neighbors(
        self,
        ref: "amkb.NodeRef",
        *,
        rel: str | list[str] | None = None,
        direction: Direction = "out",
        depth: int = 1,
        include_retired: bool = False,
        limit: int = 100,
    ) -> list["amkb.NodeRef"]:
        """Graph walk from ``ref`` (L4a). See design doc §5.3 / §5.6."""
        with boundary():
            return self._bridge.run(
                self._neighbors_async(
                    ref,
                    rel=rel,
                    direction=direction,
                    depth=depth,
                    include_retired=include_retired,
                    limit=limit,
                )
            )

    def retrieve(
        self,
        intent: str,
        *,
        k: int = 10,
        layer: str | list[str] | None = None,
        filters: "Filter | None" = None,
    ) -> "list[amkb.RetrievalHit]":
        """Intent-driven retrieval (L4b). See design doc §5.9."""
        with boundary():
            return self._bridge.run(
                self._retrieve_async(intent, k=k, layer=layer, filters=filters)
            )

    # -- History -------------------------------------------------------

    def history(
        self,
        *,
        since: Timestamp | None = None,
        until: Timestamp | None = None,
        actor: ActorId | None = None,
        tag: str | None = None,
        limit: int = 100,
    ) -> list[ChangeSetRef]:
        """List committed ChangeSet refs filtered by time / actor / tag."""
        with boundary():
            return self._bridge.run(
                self._history_async(
                    since=since, until=until, actor=actor, tag=tag, limit=limit,
                )
            )

    def get_changeset(self, ref: ChangeSetRef) -> ChangeSet:
        """Rebuild a committed ChangeSet from its event-log rows."""
        with boundary():
            return self._bridge.run(self._get_changeset_async(ref))

    def diff(self, from_ts: Timestamp, to_ts: Timestamp) -> list[Event]:
        """Events committed strictly within ``(from_ts, to_ts]`` (L2)."""
        with boundary():
            return self._bridge.run(
                self._diff_async(from_ts=from_ts, to_ts=to_ts)
            )

    def revert(
        self, target: Any, *, reason: str, actor: "amkb.Actor",
    ) -> "amkb.ChangeSet":
        # L3 only — v0.7.1 advertises supports_merge_revert=False.
        raise EConstraint(
            "Spikuit v0.7.1 does not support revert "
            "(supports_merge_revert=False)."
        )

    # -- Events --------------------------------------------------------

    def events(
        self, *, since: Timestamp | None = None, follow: bool = False,
    ) -> "Iterator[Event]":
        """Iterate events from ``since`` forward (``follow=True`` deferred)."""
        if follow:
            raise EConstraint(
                "follow=True is not supported in Spikuit v0.7.1 "
                "(see design doc §5.11)."
            )
        with boundary():
            evts = self._bridge.run(self._events_async(since=since))
        yield from evts

    # ==================================================================
    # Async implementation bodies
    # ==================================================================

    async def _get_node_async(self, ref: "amkb.NodeRef") -> Node:
        raw = str(ref)
        if raw.startswith("n-"):
            neuron = await self._circuit.get_neuron(raw, include_retired=True)
            if neuron is None:
                raise ENodeNotFound(f"node not found: {ref}", ref=ref)
            last_reviewed, due = await self._fetch_fsrs_attrs(raw)
            return neuron_to_node(
                neuron, last_reviewed_at=last_reviewed, due_at=due,
            )
        if raw.startswith("s-"):
            source = await self._circuit.get_source(raw)
            if source is None:
                raise ENodeNotFound(f"node not found: {ref}", ref=ref)
            return source_to_node(source)
        raise ENodeNotFound(f"unrecognized node ref prefix: {ref}", ref=ref)

    async def _get_edge_async(self, ref: "amkb.EdgeRef") -> Edge:
        raw = str(ref)
        if raw.startswith("e-"):
            edge = await self._find_synapse_edge_by_ref(ref)
            if edge is None:
                raise EEdgeNotFound(f"edge not found: {ref}", ref=ref)
            return edge
        if raw.startswith("j-"):
            edge = await self._find_junction_edge_by_ref(ref)
            if edge is None:
                raise EEdgeNotFound(f"edge not found: {ref}", ref=ref)
            return edge
        raise EEdgeNotFound(f"unrecognized edge ref prefix: {ref}", ref=ref)

    async def _find_by_attr_async(
        self,
        attributes: dict[str, Any],
        *,
        kind: str | None,
        layer: str | None,
        include_retired: bool,
        limit: int,
    ) -> list[NodeRef]:
        # Sources and concepts live in separate tables; scan each kind
        # only when it's in scope.
        out: list[NodeRef] = []

        want_concept = kind in (None, KIND_CONCEPT) and layer in (None, LAYER_CONCEPT)
        want_source = kind in (None, KIND_SOURCE) and layer in (None, LAYER_SOURCE)

        if want_concept:
            neurons = await self._circuit.list_neurons(
                limit=max(limit * 4, limit),
                include_retired=include_retired,
            )
            for neuron in neurons:
                last_reviewed, due = await self._fetch_fsrs_attrs(neuron.id)
                node = neuron_to_node(
                    neuron, last_reviewed_at=last_reviewed, due_at=due,
                )
                if _node_matches_attrs(node, attributes):
                    out.append(node.ref)
                    if len(out) >= limit:
                        return out

        if want_source:
            sources = await self._circuit.list_sources(limit=max(limit * 4, limit))
            for source in sources:
                if not include_retired and source.retired_at is not None:
                    continue
                node = source_to_node(source)
                if _node_matches_attrs(node, attributes):
                    out.append(node.ref)
                    if len(out) >= limit:
                        return out

        return out

    async def _neighbors_async(
        self,
        ref: NodeRef,
        *,
        rel: str | list[str] | None,
        direction: Direction,
        depth: int,
        include_retired: bool,
        limit: int,
    ) -> list[NodeRef]:
        raw = str(ref)
        if not raw.startswith("n-"):
            # Source-origin traversals are scoped out of v0.7.1 — junction
            # walks flow concept → source only. Mirrors DictStore.
            return []

        wanted_rels: set[str] | None = None
        if rel is not None:
            wanted_rels = {rel} if isinstance(rel, str) else set(rel)

        seen: set[str] = {raw}
        frontier: list[str] = [raw]
        results: list[NodeRef] = []

        for _ in range(max(depth, 0)):
            next_frontier: list[str] = []
            for nid in frontier:
                edges = await self._outgoing_synapse_edges(
                    nid, direction=direction, include_retired=include_retired,
                )
                for edge in edges:
                    if wanted_rels is not None and edge.rel not in wanted_rels:
                        continue
                    other = edge.dst if direction != "in" and edge.src == nid else edge.src
                    other_raw = str(other)
                    if other_raw not in seen:
                        seen.add(other_raw)
                        results.append(other)
                        next_frontier.append(other_raw)
                        if len(results) >= limit:
                            return results

                # Concept → source junction edges (only for out/both).
                if direction in ("out", "both") and (
                    wanted_rels is None or "derived_from" in wanted_rels
                ):
                    source_ids = await self._circuit.get_sources_for_neuron(nid)
                    for src in source_ids:
                        if src.id in seen:
                            continue
                        if not include_retired and src.retired_at is not None:
                            continue
                        seen.add(src.id)
                        results.append(source_node_ref(src.id))
                        if len(results) >= limit:
                            return results
            frontier = next_frontier

        return results

    async def _retrieve_async(
        self,
        intent: str,
        *,
        k: int,
        layer: str | list[str] | None,
        filters: "Filter | None",
    ) -> list[RetrievalHit]:
        # Layer filter: Sources are not retrievable per spec §2.2.9, and
        # Circuit.retrieve only returns concepts — so the layer argument
        # narrows the candidate space only when the caller explicitly
        # asked for source layer, in which case we return nothing.
        if layer is not None:
            wanted = {layer} if isinstance(layer, str) else set(layer)
            if LAYER_CONCEPT not in wanted:
                return []

        scored = await self._circuit.retrieve_scored(intent, limit=max(k * 4, k))

        hits: list[RetrievalHit] = []
        for neuron, score in scored:
            if filters is not None:
                last_reviewed, due = await self._fetch_fsrs_attrs(neuron.id)
                node = neuron_to_node(
                    neuron, last_reviewed_at=last_reviewed, due_at=due,
                )
                if not filter_evaluate(filters, node.attrs):
                    continue
            hits.append(
                RetrievalHit(ref=neuron_node_ref(neuron.id), score=score)
            )
            if len(hits) >= k:
                break
        return hits

    async def _history_async(
        self,
        *,
        since: Timestamp | None,
        until: Timestamp | None,
        actor: ActorId | None,
        tag: str | None,
        limit: int,
    ) -> list[ChangeSetRef]:
        rows = await self._circuit._db.list_changesets(
            since=_timestamp_to_iso(since),
            until=_timestamp_to_iso(until),
            actor_id=str(actor) if actor is not None else None,
            tag=tag,
            limit=limit,
        )
        return [ChangeSetRef(row["id"]) for row in rows]

    async def _get_changeset_async(self, ref: ChangeSetRef) -> ChangeSet:
        row = await self._circuit._db.get_changeset(str(ref))
        if row is None:
            from amkb.errors import EChangesetNotFound

            raise EChangesetNotFound(f"changeset not found: {ref}")
        event_rows = await self._circuit._db.list_events(
            changeset_id=str(ref), limit=10_000,
        )
        events = await translate_event_rows(event_rows, circuit=self._circuit)
        committed_at = _iso_to_timestamp(row["committed_at"]) or Timestamp(0)
        return ChangeSet(
            ref=ref,
            tx_ref=TransactionRef(row["id"]),
            tag=row["tag"] or "",
            actor=ActorId(row["actor_id"]),
            committed_at=committed_at,
            events=tuple(events),
        )

    async def _diff_async(
        self, *, from_ts: Timestamp, to_ts: Timestamp,
    ) -> list[Event]:
        # Pull every changeset committed in (from_ts, to_ts], flatten
        # their event rows, then translate.
        rows = await self._circuit._db.list_changesets(
            since=_timestamp_to_iso(Timestamp(int(from_ts) + 1)),
            until=_timestamp_to_iso(to_ts),
            limit=10_000,
        )
        all_events: list[Event] = []
        for cs in rows:
            event_rows = await self._circuit._db.list_events(
                changeset_id=cs["id"], limit=10_000,
            )
            translated = await translate_event_rows(event_rows, circuit=self._circuit)
            all_events.extend(translated)
        return all_events

    async def _events_async(
        self, *, since: Timestamp | None,
    ) -> list[Event]:
        rows = await self._circuit._db.list_changesets(
            since=_timestamp_to_iso(since) if since is not None else None,
            limit=10_000,
        )
        all_events: list[Event] = []
        for cs in rows:
            event_rows = await self._circuit._db.list_events(
                changeset_id=cs["id"], limit=10_000,
            )
            translated = await translate_event_rows(event_rows, circuit=self._circuit)
            all_events.extend(translated)
        return all_events

    # ==================================================================
    # Helpers
    # ==================================================================

    async def _fetch_fsrs_attrs(
        self, neuron_id: str,
    ) -> tuple[datetime | None, datetime | None]:
        """Pull ``last_reviewed_at`` / ``due_at`` from the FSRS card."""
        raw = await self._circuit._db.get_fsrs_card_json(neuron_id)
        if raw is None:
            return None, None
        import json as _json

        try:
            card = _json.loads(raw)
        except _json.JSONDecodeError:
            return None, None
        return (
            _maybe_parse_dt(card.get("last_review")),
            _maybe_parse_dt(card.get("due")),
        )

    async def _outgoing_synapse_edges(
        self,
        neuron_id: str,
        *,
        direction: Direction,
        include_retired: bool,
    ) -> list[Edge]:
        """Return synapse-derived AMKB edges incident to ``neuron_id``."""
        edges: list[Edge] = []
        if direction in ("out", "both"):
            synapses = await self._circuit._db.get_synapses_from(
                neuron_id, include_retired=include_retired,
            )
            edges.extend(self._synapses_to_edges(synapses))
        if direction in ("in", "both"):
            synapses = await self._circuit._db.get_synapses_to(
                neuron_id, include_retired=include_retired,
            )
            edges.extend(self._synapses_to_edges(synapses))
        return edges

    @staticmethod
    def _synapses_to_edges(synapses: list[Synapse]) -> list[Edge]:
        from spikuit_agents.amkb.mapping import synapse_to_edge

        out: list[Edge] = []
        for syn in synapses:
            if syn.type == SynapseType.SUMMARIZES:
                continue
            out.append(synapse_to_edge(syn))
        return out

    async def _find_synapse_edge_by_ref(self, ref: EdgeRef) -> Edge | None:
        from spikuit_agents.amkb.mapping import synapse_to_edge

        rows = await self._circuit._db.get_all_synapses(include_retired=True)
        for syn in rows:
            if syn.type == SynapseType.SUMMARIZES:
                continue
            if edge_ref_for_synapse(syn) == ref:
                return synapse_to_edge(syn)
        return None

    async def _find_junction_edge_by_ref(self, ref: EdgeRef) -> Edge | None:
        from spikuit_agents.amkb.mapping import junction_edge_ref

        # Scan every source's attached neurons and hash-match the ref.
        sources = await self._circuit.list_sources(limit=10_000)
        for source in sources:
            neuron_ids = await self._circuit._db.get_neurons_for_source(source.id)
            for nid in neuron_ids:
                if junction_edge_ref(nid, source.id) == ref:
                    neuron = await self._circuit.get_neuron(nid, include_retired=True)
                    if neuron is None:
                        return None
                    retired = (
                        neuron.retired_at is not None or source.retired_at is not None
                    )
                    return junction_edge(
                        neuron_id=nid,
                        source_id=source.id,
                        created_at=neuron.created_at,
                        retired=retired,
                    )
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _node_matches_attrs(node: Node, attributes: dict[str, Any]) -> bool:
    """Equality match used by ``find_by_attr`` (spec §3.4.2)."""
    return all(node.attrs.get(k) == v for k, v in attributes.items())


def _iso_to_timestamp(iso: str | None) -> Timestamp | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime_to_timestamp(dt)


def _maybe_parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    return None
