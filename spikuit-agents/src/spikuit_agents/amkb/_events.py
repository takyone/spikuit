"""Spikuit event log → AMKB ``Event`` translator.

The v0.7.0 event log stores rows with
``(id, changeset_id, seq, op, target_kind, target_id, before_json,
after_json, at)``. This module rebuilds :class:`amkb.Event` instances
from those rows, routing both Neuron and Synapse rows through the
:mod:`spikuit_agents.amkb.mapping` codecs so the canonical snapshot
shape stays in one place (see design doc §5.7).

``op → kind`` translation table
---------------------------------

| Spikuit ``op``        | AMKB ``kind``     |
|-----------------------|-------------------|
| ``neuron.add``        | ``node.created``  |
| ``neuron.update``     | ``node.rewritten``|
| ``neuron.retire``     | ``node.retired``  |
| ``neuron.merge``      | ``node.merged``   |
| ``synapse.add``       | ``edge.created``  |
| ``synapse.retire``    | ``edge.retired``  |
| ``synapse.update``    | *(dropped)*       |

``synapse.update`` rows carry STDP weight bumps, which have no AMKB
event kind (§4.3.C keeps STDP off the public surface). The translator
drops them silently.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import msgspec
from amkb.refs import EdgeRef, NodeRef
from amkb.snapshots import edge_snapshot, node_snapshot
from amkb.types import Event

from spikuit_core.models import Neuron, Source, Synapse, SynapseType
from spikuit_core.transactions import (
    OP_NEURON_ADD,
    OP_NEURON_MERGE,
    OP_NEURON_RETIRE,
    OP_NEURON_UPDATE,
    OP_SYNAPSE_ADD,
    OP_SYNAPSE_RETIRE,
    OP_SYNAPSE_UPDATE,
)

from spikuit_agents.amkb.mapping import (
    edge_ref_for_synapse,
    neuron_node_ref,
    neuron_to_node,
    source_node_ref,
    source_to_node,
    synapse_to_edge,
)

# Adapter-private op strings for source lifecycle events. The v0.7.0
# event log does not emit these from the core; the v0.7.1 adapter's
# transaction wrapper injects them manually via current_transaction.emit
# so the AMKB change-set rehydration still sees ``node.created`` /
# ``node.retired`` for Source nodes.
OP_SOURCE_ADD = "source.add"
OP_SOURCE_RETIRE = "source.retire"

if TYPE_CHECKING:
    from spikuit_core import Circuit


__all__ = ["translate_event_row", "translate_event_rows"]


_NEURON_OP_TO_KIND: dict[str, str] = {
    OP_NEURON_ADD: "node.created",
    OP_NEURON_UPDATE: "node.rewritten",
    OP_NEURON_RETIRE: "node.retired",
    OP_NEURON_MERGE: "node.merged",
}

_SYNAPSE_OP_TO_KIND: dict[str, str] = {
    OP_SYNAPSE_ADD: "edge.created",
    OP_SYNAPSE_RETIRE: "edge.retired",
    # OP_SYNAPSE_UPDATE intentionally omitted — STDP weight bumps
    # have no AMKB event kind.
}


def _neuron_snapshot_from_json(raw: str | None) -> dict[str, Any] | None:
    """Decode a stored neuron snapshot JSON into an AMKB node_snapshot dict."""
    if raw is None:
        return None
    neuron = msgspec.json.decode(raw, type=Neuron)
    return node_snapshot(neuron_to_node(neuron))


def _source_snapshot_from_json(raw: str | None) -> dict[str, Any] | None:
    """Decode a stored source snapshot JSON into an AMKB node_snapshot dict."""
    if raw is None:
        return None
    source = msgspec.json.decode(raw, type=Source)
    return node_snapshot(source_to_node(source))


def _synapse_snapshot_from_json(raw: str | None) -> dict[str, Any] | None:
    """Decode a stored synapse snapshot JSON into an AMKB edge_snapshot dict.

    Returns ``None`` for SUMMARIZES rows (filtered per §4.3.A) so callers
    can treat the whole event as dropped.
    """
    if raw is None:
        return None
    synapse = msgspec.json.decode(raw, type=Synapse)
    if synapse.type == SynapseType.SUMMARIZES:
        return None
    return edge_snapshot(synapse_to_edge(synapse))


def _parse_synapse_target(target_id: str) -> tuple[str, str, SynapseType] | None:
    """Split a ``pre|post|type`` synapse target id, or return ``None``."""
    parts = target_id.split("|")
    if len(parts) != 3:
        return None
    pre, post, type_str = parts
    try:
        syn_type = SynapseType(type_str)
    except ValueError:
        return None
    return pre, post, syn_type


async def _lookup_synapse_for_retire(
    circuit: "Circuit", pre: str, post: str, syn_type: SynapseType,
) -> Synapse | None:
    """Best-effort synapse lookup for events that don't carry a snapshot.

    ``OP_SYNAPSE_RETIRE`` rows have neither ``before_json`` nor
    ``after_json``; we read the current (retired) row to reconstruct
    the EdgeRef via the composite key + ``created_at``.
    """
    return await circuit.get_synapse(pre, post, syn_type, include_retired=True)


async def _lookup_neuron_for_retire(
    circuit: "Circuit", neuron_id: str,
) -> Neuron | None:
    """Best-effort neuron lookup for ``OP_NEURON_RETIRE`` rows."""
    return await circuit.get_neuron(neuron_id, include_retired=True)


async def translate_event_row(row: dict[str, Any], *, circuit: "Circuit") -> Event | None:
    """Translate one ``event`` table row to an AMKB :class:`Event`.

    Returns ``None`` when the row has no AMKB equivalent — this happens
    for STDP ``synapse.update`` bumps and for ``SUMMARIZES`` synapse
    rows that §4.3.A hides from the adapter surface.
    """
    op = row["op"]
    target_kind = row["target_kind"]
    target_id = row["target_id"]
    before_json = row["before_json"]
    after_json = row["after_json"]

    # -- Neuron-side ops ---------------------------------------------
    if target_kind == "neuron":
        kind = _NEURON_OP_TO_KIND.get(op)
        if kind is None:
            return None

        before: dict[str, Any] | None = None
        after: dict[str, Any] | None = None
        meta: dict[str, Any] = {}

        if op == OP_NEURON_MERGE:
            before = _neuron_snapshot_from_json(before_json)
            if after_json is not None:
                merge_payload = json.loads(after_json)
                meta["ancestors"] = merge_payload.get("sources", [])
                merged_after = merge_payload.get("after")
                if merged_after is not None:
                    after = _neuron_snapshot_from_json(
                        msgspec.json.encode(merged_after).decode()
                    )
        elif op == OP_NEURON_RETIRE:
            # RETIRE rows carry no JSON — pull the tombstoned neuron so
            # the snapshot shows state="retired".
            neuron = await _lookup_neuron_for_retire(circuit, target_id)
            if neuron is not None:
                before = node_snapshot(
                    neuron_to_node(msgspec.structs.replace(neuron, retired_at=None))
                )
                after = node_snapshot(neuron_to_node(neuron))
        else:
            before = _neuron_snapshot_from_json(before_json)
            after = _neuron_snapshot_from_json(after_json)

        target: NodeRef | EdgeRef = neuron_node_ref(target_id)
        return Event(
            kind=kind,  # type: ignore[arg-type]
            target=target,
            before=before,
            after=after,
            meta=meta,
        )

    # -- Source-side ops ---------------------------------------------
    if target_kind == "source":
        if op == OP_SOURCE_ADD:
            after = _source_snapshot_from_json(after_json)
            if after is None:
                return None
            return Event(
                kind="node.created",  # type: ignore[arg-type]
                target=source_node_ref(target_id),
                before=None,
                after=after,
            )
        if op == OP_SOURCE_RETIRE:
            before = _source_snapshot_from_json(before_json)
            after = _source_snapshot_from_json(after_json)
            return Event(
                kind="node.retired",  # type: ignore[arg-type]
                target=source_node_ref(target_id),
                before=before,
                after=after,
            )
        return None

    # -- Synapse-side ops --------------------------------------------
    if target_kind == "synapse":
        if op == OP_SYNAPSE_UPDATE:
            return None  # STDP weight bumps — dropped per §4.3.C
        kind = _SYNAPSE_OP_TO_KIND.get(op)
        if kind is None:
            return None

        parsed = _parse_synapse_target(target_id)
        if parsed is None:
            return None
        pre, post, syn_type = parsed
        if syn_type == SynapseType.SUMMARIZES:
            return None

        if op == OP_SYNAPSE_ADD:
            after = _synapse_snapshot_from_json(after_json)
            if after is None:
                return None
            return Event(
                kind="edge.created",  # type: ignore[arg-type]
                target=EdgeRef(after["ref"]),
                before=None,
                after=after,
            )

        # OP_SYNAPSE_RETIRE — no JSON payload, fetch current state.
        synapse = await _lookup_synapse_for_retire(circuit, pre, post, syn_type)
        if synapse is None:
            return None
        after = edge_snapshot(synapse_to_edge(synapse))
        return Event(
            kind="edge.retired",  # type: ignore[arg-type]
            target=edge_ref_for_synapse(synapse),
            before=None,
            after=after,
        )

    return None


async def translate_event_rows(
    rows: list[dict[str, Any]], *, circuit: "Circuit",
) -> list[Event]:
    """Translate a batch of event rows, skipping rows with no AMKB equivalent."""
    out: list[Event] = []
    for row in rows:
        evt = await translate_event_row(row, circuit=circuit)
        if evt is not None:
            out.append(evt)
    return out
