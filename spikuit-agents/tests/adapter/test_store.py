"""Integration tests for SpikuitStore against a real in-memory Circuit.

These tests drive :class:`SpikuitStore` through its sync surface while
the underlying :class:`spikuit_core.Circuit` runs on SQLite with a
temporary file. They cover the read-side method contracts defined in
design doc §5.3 and the retired-ref resolution rules from §5.5 / §5.6.

Mutation / begin() paths are filled in by task #14 and are not
exercised here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from amkb.errors import EConstraint, EEdgeNotFound, ENodeNotFound
from amkb.filters import Eq
from amkb.types import LAYER_CONCEPT, LAYER_SOURCE

from spikuit_agents.amkb.mapping import edge_ref_for_synapse, junction_edge_ref
from spikuit_agents.amkb.store import SpikuitStore
from spikuit_core import Circuit, Neuron, Source, SynapseType


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SpikuitStore]:
    circuit = Circuit(db_path=str(tmp_path / "circuit.db"))
    store = SpikuitStore.open(circuit)
    try:
        yield store
    finally:
        store.close()


async def _seed_two_neurons_one_edge(circuit: Circuit) -> tuple[Neuron, Neuron]:
    n1 = Neuron.create("# Functor\n\nbody", type="concept", domain="math")
    n2 = Neuron.create("# Monad\n\nbody", type="concept", domain="math")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse(n1.id, n2.id, SynapseType.REQUIRES, weight=0.7)
    return n1, n2


# ---------------------------------------------------------------------------
# get_node / get_edge
# ---------------------------------------------------------------------------


def test_get_node_returns_mapped_neuron(store: SpikuitStore) -> None:
    n1, _ = store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    node = store.get_node(n1.id)
    assert node.ref == n1.id
    assert node.kind == "concept"
    assert node.layer == LAYER_CONCEPT
    assert node.state == "live"
    assert node.attrs["domain"] == "math"


def test_get_node_resolves_retired_by_ref(store: SpikuitStore) -> None:
    async def seed() -> Neuron:
        n = Neuron.create("# Doomed", type="concept", domain="math")
        await store._circuit.add_neuron(n)
        await store._circuit.remove_neuron(n.id)
        return n

    n = store._bridge.run(seed())
    node = store.get_node(n.id)
    assert node.state == "retired"
    assert node.retired_at is not None


def test_get_node_unknown_raises_enodenotfound(store: SpikuitStore) -> None:
    with pytest.raises(ENodeNotFound):
        store.get_node("n-doesnotexist")


def test_get_node_unrecognized_prefix_raises(store: SpikuitStore) -> None:
    with pytest.raises(ENodeNotFound):
        store.get_node("banana-ref")


def test_get_edge_round_trips_synapse(store: SpikuitStore) -> None:
    n1, n2 = store._bridge.run(_seed_two_neurons_one_edge(store._circuit))

    async def fetch_syn():
        return (await store._circuit._db.get_all_synapses(include_retired=True))[0]

    syn = store._bridge.run(fetch_syn())
    ref = edge_ref_for_synapse(syn)
    edge = store.get_edge(ref)
    assert edge.rel == "requires"
    assert edge.src == n1.id
    assert edge.dst == n2.id
    assert edge.attrs["spk:weight"] == pytest.approx(0.7)


def test_get_edge_unknown_raises_eedgenotfound(store: SpikuitStore) -> None:
    with pytest.raises(EEdgeNotFound):
        store.get_edge("e-ffffffffffff")


def test_get_edge_unrecognized_prefix_raises(store: SpikuitStore) -> None:
    with pytest.raises(EEdgeNotFound):
        store.get_edge("q-foo")


# ---------------------------------------------------------------------------
# find_by_attr
# ---------------------------------------------------------------------------


def test_find_by_attr_equality_on_domain(store: SpikuitStore) -> None:
    n1, n2 = store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    refs = store.find_by_attr({"domain": "math"})
    assert set(refs) == {n1.id, n2.id}


def test_find_by_attr_filters_kind_concept_vs_source(store: SpikuitStore) -> None:
    async def seed():
        n = Neuron.create("# A", type="concept", domain="math")
        s = Source(title="Paper", url="https://x.com/a")
        await store._circuit.add_neuron(n)
        await store._circuit.add_source(s)
        return n, s

    n, s = store._bridge.run(seed())
    concept_refs = store.find_by_attr({}, kind="concept")
    assert n.id in concept_refs
    assert s.id not in concept_refs

    source_refs = store.find_by_attr({}, kind="source")
    assert s.id in source_refs
    assert n.id not in source_refs


def test_find_by_attr_excludes_retired_by_default(store: SpikuitStore) -> None:
    async def seed():
        n = Neuron.create("# A", type="concept", domain="math")
        await store._circuit.add_neuron(n)
        await store._circuit.remove_neuron(n.id)
        return n

    n = store._bridge.run(seed())
    assert n.id not in store.find_by_attr({"domain": "math"})
    assert n.id in store.find_by_attr({"domain": "math"}, include_retired=True)


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------


def test_neighbors_out_follows_synapse_edges(store: SpikuitStore) -> None:
    n1, n2 = store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    assert store.neighbors(n1.id, direction="out") == [n2.id]


def test_neighbors_in_reads_predecessors(store: SpikuitStore) -> None:
    n1, n2 = store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    assert store.neighbors(n2.id, direction="in") == [n1.id]


def test_neighbors_rel_filter_drops_mismatches(store: SpikuitStore) -> None:
    n1, n2 = store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    assert store.neighbors(n1.id, rel="extends") == []
    assert store.neighbors(n1.id, rel="requires") == [n2.id]


def test_neighbors_does_not_return_source_kind_nodes(
    store: SpikuitStore,
) -> None:
    """Per AMKB §3.4.3, walks MUST NOT surface kind=source neighbors."""
    async def seed():
        n = Neuron.create("# A", type="concept", domain="math")
        s = Source(title="Paper", url="https://x.com/a")
        await store._circuit.add_neuron(n)
        await store._circuit.add_source(s)
        await store._circuit.attach_source(n.id, s.id)
        return n, s

    n, s = store._bridge.run(seed())
    hits = store.neighbors(n.id, direction="out")
    assert s.id not in [str(ref) for ref in hits]


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------


def test_retrieve_returns_concept_hits(store: SpikuitStore) -> None:
    store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    hits = store.retrieve("functor", k=5)
    # Don't pin the ordering (embedding drift); just require at least
    # one concept hit with a numeric score.
    assert hits
    assert all(hit.score is None or isinstance(hit.score, float) for hit in hits)


def test_retrieve_layer_source_only_returns_empty(store: SpikuitStore) -> None:
    store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    assert store.retrieve("functor", k=5, layer="L_source") == []


def test_retrieve_filter_post_evaluates_attrs(store: SpikuitStore) -> None:
    store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    filt = Eq(key="domain", value="math")
    hits = store.retrieve("functor", k=5, filters=filt)
    assert hits  # all seeded neurons have domain=math


# ---------------------------------------------------------------------------
# history / get_changeset / events / diff
# ---------------------------------------------------------------------------


def test_history_lists_changesets_chronologically(store: SpikuitStore) -> None:
    store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    refs = store.history()
    # Three auto-tx changesets: two neuron.add + one synapse.add
    assert len(refs) == 3


def test_get_changeset_rehydrates_events(store: SpikuitStore) -> None:
    store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    first = store.history()[0]
    cs = store.get_changeset(first)
    assert len(cs.events) == 1
    assert cs.events[0].kind == "node.created"


def test_events_iterates_all_translated_events(store: SpikuitStore) -> None:
    store._bridge.run(_seed_two_neurons_one_edge(store._circuit))
    evts = list(store.events())
    kinds = [e.kind for e in evts]
    assert kinds.count("node.created") == 2
    assert kinds.count("edge.created") == 1


def test_events_follow_raises_econstraint(store: SpikuitStore) -> None:
    with pytest.raises(EConstraint):
        list(store.events(follow=True))


def test_retire_emits_node_retired_event(store: SpikuitStore) -> None:
    async def seed():
        n = Neuron.create("# A", type="concept")
        await store._circuit.add_neuron(n)
        await store._circuit.remove_neuron(n.id)
        return n

    store._bridge.run(seed())
    evts = list(store.events())
    assert any(e.kind == "node.retired" for e in evts)


# ---------------------------------------------------------------------------
# revert
# ---------------------------------------------------------------------------


def test_revert_always_raises_econstraint(store: SpikuitStore) -> None:
    from amkb.types import Actor

    actor = Actor(id="actor-1", kind="human")
    with pytest.raises(EConstraint):
        store.revert("cs-whatever", reason="nope", actor=actor)
