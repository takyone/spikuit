"""Tests for merge lineage + OP_NEURON_MERGE emission — AMKB v0.7.0."""

from __future__ import annotations

import pytest
import pytest_asyncio

from spikuit_core.circuit import Circuit
from spikuit_core.models import Neuron
from spikuit_core.transactions import OP_NEURON_MERGE, OP_NEURON_RETIRE


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "merge.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_merge_writes_predecessor_rows(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    t = Neuron.create("Target")
    for n in (a, b, t):
        await circuit.add_neuron(n)

    await circuit.merge_neurons([a.id, b.id], t.id)

    parents = await circuit.predecessors_of_lineage(t.id)
    assert set(parents) == {a.id, b.id}


@pytest.mark.asyncio
async def test_merge_emits_single_merge_event_and_retire_events(circuit):
    a = Neuron.create("A")
    t = Neuron.create("Target")
    await circuit.add_neuron(a)
    await circuit.add_neuron(t)

    await circuit.merge_neurons([a.id], t.id)

    all_events = await circuit._db.list_events()
    merge_events = [e for e in all_events if e["op"] == OP_NEURON_MERGE]
    retire_events = [e for e in all_events if e["op"] == OP_NEURON_RETIRE]
    assert len(merge_events) == 1
    assert merge_events[0]["target_id"] == t.id
    assert a.id in merge_events[0]["after_json"]
    assert any(e["target_id"] == a.id for e in retire_events)


@pytest.mark.asyncio
async def test_merge_events_share_one_changeset(circuit):
    a = Neuron.create("A")
    t = Neuron.create("Target")
    await circuit.add_neuron(a)
    await circuit.add_neuron(t)

    await circuit.merge_neurons([a.id], t.id)

    all_events = await circuit._db.list_events()
    merge_event = next(e for e in all_events if e["op"] == OP_NEURON_MERGE)
    cs_id = merge_event["changeset_id"]
    # Retire event for source must belong to the same changeset.
    retire_for_a = next(
        e for e in all_events
        if e["op"] == OP_NEURON_RETIRE and e["target_id"] == a.id
    )
    assert retire_for_a["changeset_id"] == cs_id


@pytest.mark.asyncio
async def test_predecessors_empty_for_plain_neuron(circuit):
    n = Neuron.create("solo")
    await circuit.add_neuron(n)
    assert await circuit.predecessors_of_lineage(n.id) == []


@pytest.mark.asyncio
async def test_merge_rejects_into_in_sources(circuit):
    t = Neuron.create("T")
    await circuit.add_neuron(t)
    with pytest.raises(ValueError):
        await circuit.merge_neurons([t.id], t.id)
