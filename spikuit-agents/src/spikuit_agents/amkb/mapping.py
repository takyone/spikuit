"""Spikuit ↔ AMKB type codecs.

Pure functions that translate Spikuit :mod:`spikuit_core.models` structs
into ``amkb.Node`` / ``amkb.Edge`` instances. See design doc §3 (Node
mapping) and §4 (Edge mapping) for the source-of-truth decisions.

The helpers are stateless. FSRS-derived attrs (``spk:last_reviewed_at``,
``spk:due_at``) and the ``storage_uri``-vs-``url`` disambiguation are
passed in by the Store layer, which has the Circuit handle to look
them up. Keeping the codec pure lets the conformance fixture exercise
it without spinning a database.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING, Any

from amkb.refs import EdgeRef, NodeRef, Timestamp
from amkb.types import (
    KIND_CONCEPT,
    KIND_SOURCE,
    LAYER_CONCEPT,
    LAYER_SOURCE,
    REL_CONTRASTS,
    REL_DERIVED_FROM,
    REL_EXTENDS,
    REL_RELATES_TO,
    REL_REQUIRES,
    Edge,
    Node,
    Rel,
)

from spikuit_core.models import SynapseType

if TYPE_CHECKING:
    from spikuit_core.models import Neuron, Source, Synapse


__all__ = [
    "SYNAPSE_TYPE_TO_REL",
    "datetime_to_timestamp",
    "edge_ref_for_synapse",
    "junction_edge",
    "junction_edge_ref",
    "neuron_node_ref",
    "neuron_to_node",
    "source_node_ref",
    "source_to_node",
    "synapse_to_edge",
]


# ---------------------------------------------------------------------------
# Synapse type → AMKB rel table (§4.3.A)
# ---------------------------------------------------------------------------


SYNAPSE_TYPE_TO_REL: dict[SynapseType, Rel] = {
    SynapseType.REQUIRES: REL_REQUIRES,
    SynapseType.EXTENDS: REL_EXTENDS,
    SynapseType.CONTRASTS: REL_CONTRASTS,
    SynapseType.RELATES_TO: REL_RELATES_TO,
    # SynapseType.SUMMARIZES intentionally omitted — filtered in v0.7.1.
}


# ---------------------------------------------------------------------------
# Timestamp conversion
# ---------------------------------------------------------------------------


def datetime_to_timestamp(dt: datetime | None) -> Timestamp | None:
    """Convert a ``datetime`` to an AMKB ``Timestamp`` (µs since epoch).

    AMKB requires timestamps to be monotonic within a store but leaves the
    unit implementation-defined (spec §2.1). Microseconds since the Unix
    epoch give us sub-millisecond resolution — enough to order mutations
    emitted in rapid succession — and fit comfortably in a 64-bit int.
    """
    if dt is None:
        return None
    return Timestamp(int(dt.timestamp() * 1_000_000))


# ---------------------------------------------------------------------------
# Ref helpers
# ---------------------------------------------------------------------------


def neuron_node_ref(neuron_id: str) -> NodeRef:
    """Wrap a Spikuit neuron id as an AMKB ``NodeRef``.

    Neuron ids already carry the ``n-`` prefix, so the adapter exposes
    them verbatim. Refs are opaque per spec §2.1; the prefix is an
    internal convention only used for the get-dispatch in §5.3.
    """
    return NodeRef(neuron_id)


def source_node_ref(source_id: str) -> NodeRef:
    """Wrap a Spikuit source id as an AMKB ``NodeRef``."""
    return NodeRef(source_id)


def edge_ref_for_synapse(synapse: "Synapse") -> EdgeRef:
    """Synthesize a stable ``EdgeRef`` for a Synapse row.

    Spikuit has no ``synapse.id`` column yet (§4.4.A), so identity is
    the composite ``(pre, post, type, created_at)``. Hashing all four
    keeps the ref stable across STDP weight bumps and collision-free
    when a synapse is retired and re-created on the same composite key
    (the new row will have a later ``created_at``).
    """
    seed = "|".join(
        [
            synapse.pre,
            synapse.post,
            synapse.type.value,
            synapse.created_at.isoformat(),
        ]
    )
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=6).hexdigest()
    return EdgeRef(f"e-{digest}")


def junction_edge_ref(neuron_id: str, source_id: str) -> EdgeRef:
    """Synthesize an ``EdgeRef`` for a ``neuron_source`` junction row (§4.5).

    The junction carries no metadata, so its identity is the endpoint
    pair. Different from the synapse hash to keep the two edge spaces
    distinct and avoid any chance of namespace collision.
    """
    seed = f"{neuron_id}|{source_id}|derived_from"
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=6).hexdigest()
    return EdgeRef(f"j-{digest}")


# ---------------------------------------------------------------------------
# Neuron → Node (§3.2–§3.4)
# ---------------------------------------------------------------------------


def neuron_to_node(
    neuron: "Neuron",
    *,
    last_reviewed_at: datetime | None = None,
    due_at: datetime | None = None,
) -> Node:
    """Translate a :class:`spikuit_core.Neuron` into an AMKB ``Node``.

    ``last_reviewed_at`` and ``due_at`` are injected by the Store layer
    because they live in the FSRS card JSON, not on the Neuron struct.
    They become ``spk:last_reviewed_at`` / ``spk:due_at`` attrs
    (§3.3.D). All other attrs come from the struct directly.
    """
    attrs: dict[str, Any] = {}
    if neuron.type is not None:
        attrs["spk:type"] = neuron.type
    if neuron.domain is not None:
        attrs["domain"] = neuron.domain
    if last_reviewed_at is not None:
        attrs["spk:last_reviewed_at"] = datetime_to_timestamp(last_reviewed_at)
    if due_at is not None:
        attrs["spk:due_at"] = datetime_to_timestamp(due_at)

    retired_ts = datetime_to_timestamp(neuron.retired_at)
    state = "retired" if retired_ts is not None else "live"

    return Node(
        ref=neuron_node_ref(neuron.id),
        kind=KIND_CONCEPT,
        layer=LAYER_CONCEPT,
        content=neuron.content,
        attrs=attrs,
        state=state,
        created_at=datetime_to_timestamp(neuron.created_at),  # type: ignore[arg-type]
        updated_at=datetime_to_timestamp(neuron.updated_at),  # type: ignore[arg-type]
        retired_at=retired_ts,
    )


# ---------------------------------------------------------------------------
# Source → Node (§3.5)
# ---------------------------------------------------------------------------


def _source_content(source: "Source") -> str:
    """Pick the ``Node.content`` label for a Source (decision S1)."""
    if source.title:
        return source.title
    if source.url:
        return source.url
    return "Untitled source"


def source_to_node(source: "Source") -> Node:
    """Translate a :class:`spikuit_core.Source` into an AMKB ``Node``.

    Implements §3.5 decisions S1–S5: label fallback for ``content``,
    ``content_ref`` pointer from url or storage_uri, reserved attrs
    (``content_hash``, ``fetched_at``) promoted to the canonical
    namespace, and all Spikuit-specific metadata published under the
    ``spk:`` prefix. ``filterable`` / ``searchable`` / ``extractor``
    are deferred (§3.7).
    """
    attrs: dict[str, Any] = {}

    content_ref = source.url if source.url else source.storage_uri
    if content_ref is not None:
        attrs["content_ref"] = content_ref

    if source.content_hash is not None:
        attrs["content_hash"] = source.content_hash
    if source.fetched_at is not None:
        attrs["fetched_at"] = datetime_to_timestamp(source.fetched_at)

    if source.title is not None:
        attrs["spk:title"] = source.title
    if source.author is not None:
        attrs["spk:author"] = source.author
    if source.section is not None:
        attrs["spk:section"] = source.section
    if source.excerpt is not None:
        attrs["spk:excerpt"] = source.excerpt
    if source.notes is not None:
        attrs["spk:notes"] = source.notes
    if source.status:
        attrs["spk:status"] = source.status
    if source.http_etag is not None:
        attrs["spk:http_etag"] = source.http_etag
    if source.http_last_modified is not None:
        attrs["spk:http_last_modified"] = source.http_last_modified
    if source.accessed_at is not None:
        attrs["spk:accessed_at"] = datetime_to_timestamp(source.accessed_at)
    if source.storage_uri is not None and source.storage_uri != source.url:
        attrs["spk:storage_uri"] = source.storage_uri

    retired_ts = datetime_to_timestamp(source.retired_at)
    state = "retired" if retired_ts is not None else "live"

    return Node(
        ref=source_node_ref(source.id),
        kind=KIND_SOURCE,
        layer=LAYER_SOURCE,
        content=_source_content(source),
        attrs=attrs,
        state=state,
        created_at=datetime_to_timestamp(source.created_at),  # type: ignore[arg-type]
        updated_at=datetime_to_timestamp(source.created_at),  # type: ignore[arg-type]
        retired_at=retired_ts,
    )


# ---------------------------------------------------------------------------
# Synapse → Edge (§4.2–§4.4)
# ---------------------------------------------------------------------------


def synapse_to_edge(synapse: "Synapse") -> Edge:
    """Translate a :class:`spikuit_core.Synapse` into an AMKB ``Edge``.

    Raises ``ValueError`` if the synapse is ``SUMMARIZES`` — those rows
    are filtered out by the Store layer before ever reaching this codec
    (§4.3.A). Raising keeps misuse loud rather than silently emitting
    an illegal edge.
    """
    try:
        rel = SYNAPSE_TYPE_TO_REL[synapse.type]
    except KeyError as exc:
        raise ValueError(
            f"Synapse type {synapse.type.value!r} has no v0.7.1 AMKB mapping; "
            "SUMMARIZES rows must be filtered before calling synapse_to_edge()"
        ) from exc

    attrs: dict[str, Any] = {
        "spk:weight": synapse.weight,
        "spk:confidence": synapse.confidence.value,
        "spk:confidence_score": synapse.confidence_score,
    }

    retired_ts = datetime_to_timestamp(synapse.retired_at)
    state = "retired" if retired_ts is not None else "live"

    return Edge(
        ref=edge_ref_for_synapse(synapse),
        rel=rel,
        src=neuron_node_ref(synapse.pre),
        dst=neuron_node_ref(synapse.post),
        attrs=attrs,
        state=state,
        created_at=datetime_to_timestamp(synapse.created_at),  # type: ignore[arg-type]
        retired_at=retired_ts,
    )


# ---------------------------------------------------------------------------
# Junction (neuron_source) → derived_from Edge (§4.5)
# ---------------------------------------------------------------------------


def junction_edge(
    *,
    neuron_id: str,
    source_id: str,
    created_at: datetime,
    retired: bool = False,
) -> Edge:
    """Render a ``neuron_source`` junction row as a ``derived_from`` Edge.

    The junction table carries no metadata, so ``created_at`` is synthesized
    from the concept neuron's creation time by the Store layer (§4.5, §9.1
    follow-up to add an explicit column). ``retired`` is derived from
    endpoint state — when either the neuron or source is retired, the
    link is effectively retired per spec §2.3.5.
    """
    ts = datetime_to_timestamp(created_at)
    retired_ts = ts if retired else None
    state = "retired" if retired else "live"
    return Edge(
        ref=junction_edge_ref(neuron_id, source_id),
        rel=REL_DERIVED_FROM,
        src=neuron_node_ref(neuron_id),
        dst=source_node_ref(source_id),
        attrs={},
        state=state,
        created_at=ts,  # type: ignore[arg-type]
        retired_at=retired_ts,
    )
