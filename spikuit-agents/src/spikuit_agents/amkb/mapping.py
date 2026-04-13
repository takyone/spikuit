"""Type mapping between Spikuit and AMKB.

Spikuit's native model (`Neuron`, `Synapse`, `SynapseType`) is richer
than the AMKB protocol shape in some places (FSRS state, STDP weights,
domains) and narrower in others (no explicit layer, no free-form
`attrs`). This module owns the lossy-but-deterministic translation in
one place.

### Neuron ↔ Node

The default Spikuit `Neuron` maps to a `kind=concept, layer=L_concept`
Node. The Spikuit fields `type` / `domain` / `source` are surfaced as
entries in `Node.attrs` so they remain queryable via `find_by_attr`.
Neurons whose `type` is `"source"` (as used by external SKILL.md import
and the future Source-as-virtual-node plan) map to
`kind=source, layer=L_source`.

### Synapse ↔ Edge

Every Spikuit `SynapseType` value is also a reserved AMKB `rel`
constant (see `types.py:25-102`), so the mapping is identity.
Bidirectional types (`contrasts`, `relates_to`) produce two Synapse
rows in Spikuit but a single AMKB Edge — the adapter uses the
pre→post row as the canonical edge and lets the reverse row follow.
"""

from __future__ import annotations

from datetime import datetime

from amkb.refs import EdgeRef, NodeRef, Timestamp
from amkb.types import (
    KIND_CONCEPT,
    KIND_SOURCE,
    LAYER_CONCEPT,
    LAYER_SOURCE,
    Edge,
    Node,
)
from spikuit_core.models import Neuron, Synapse, SynapseType

from spikuit_agents.amkb._ids import encode_edge_ref


def dt_to_ts(dt: datetime) -> Timestamp:
    """AMKB Timestamp is a monotonic int. Use microseconds since epoch."""
    return Timestamp(int(dt.timestamp() * 1_000_000))


def neuron_to_node(
    neuron: Neuron,
    *,
    retired_at: datetime | None = None,
) -> Node:
    is_source = neuron.type == "source"
    kind = KIND_SOURCE if is_source else KIND_CONCEPT
    layer = LAYER_SOURCE if is_source else LAYER_CONCEPT
    attrs: dict[str, object] = {}
    if neuron.type is not None:
        attrs["type"] = neuron.type
    if neuron.domain is not None:
        attrs["domain"] = neuron.domain
    if neuron.source is not None:
        attrs["source"] = neuron.source
    return Node(
        ref=NodeRef(neuron.id),
        kind=kind,
        layer=layer,
        content=neuron.content,
        attrs=attrs,
        state="retired" if retired_at is not None else "live",
        created_at=dt_to_ts(neuron.created_at),
        updated_at=dt_to_ts(neuron.updated_at),
        retired_at=dt_to_ts(retired_at) if retired_at is not None else None,
    )


def synapse_to_edge(
    synapse: Synapse,
    *,
    retired_at: datetime | None = None,
) -> Edge:
    rel = synapse.type.value
    return Edge(
        ref=encode_edge_ref(synapse.pre, synapse.post, rel),
        rel=rel,
        src=NodeRef(synapse.pre),
        dst=NodeRef(synapse.post),
        attrs={
            "weight": synapse.weight,
            "confidence": synapse.confidence.value,
            "confidence_score": synapse.confidence_score,
        },
        state="retired" if retired_at is not None else "live",
        created_at=dt_to_ts(synapse.created_at),
        retired_at=dt_to_ts(retired_at) if retired_at is not None else None,
    )


def rel_to_synapse_type(rel: str) -> SynapseType:
    try:
        return SynapseType(rel)
    except ValueError as exc:
        raise ValueError(f"unsupported rel for Spikuit backend: {rel!r}") from exc
