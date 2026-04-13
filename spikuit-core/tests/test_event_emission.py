"""Tests for auto-commit event emission on Circuit mutators — v0.7.0."""

from __future__ import annotations

import pytest
import pytest_asyncio

from spikuit_core.circuit import Circuit
from spikuit_core.models import Neuron, SynapseType
from spikuit_core.transactions import (
    OP_NEURON_ADD,
    OP_NEURON_UPDATE,
    OP_SYNAPSE_ADD,
    OP_SYNAPSE_RETIRE,
    OP_SYNAPSE_UPDATE,
)


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "ev.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_add_neuron_emits_event(circuit):
    n = Neuron.create("# A")
    await circuit.add_neuron(n)
    events = await circuit._db.list_events(target_id=n.id)
    assert len(events) == 1
    assert events[0]["op"] == OP_NEURON_ADD
    assert events[0]["after_json"] is not None
    assert n.id in events[0]["after_json"]


@pytest.mark.asyncio
async def test_update_neuron_emits_event_with_before_after(circuit):
    n = Neuron.create("old content")
    await circuit.add_neuron(n)
    n.content = "new content"
    await circuit.update_neuron(n)

    update_events = [
        e for e in await circuit._db.list_events(target_id=n.id)
        if e["op"] == OP_NEURON_UPDATE
    ]
    assert len(update_events) == 1
    assert "old content" in update_events[0]["before_json"]
    assert "new content" in update_events[0]["after_json"]


@pytest.mark.asyncio
async def test_add_directional_synapse_emits_one_event(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.REQUIRES)

    events = await circuit._db.list_events(
        target_id=f"{a.id}|{b.id}|{SynapseType.REQUIRES.value}",
    )
    assert len(events) == 1
    assert events[0]["op"] == OP_SYNAPSE_ADD


@pytest.mark.asyncio
async def test_add_bidirectional_synapse_emits_two_events(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.RELATES_TO)

    all_events = await circuit._db.list_events()
    add_events = [e for e in all_events if e["op"] == OP_SYNAPSE_ADD]
    assert len(add_events) == 2


@pytest.mark.asyncio
async def test_remove_synapse_emits_retire_event(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.REQUIRES)
    await circuit.remove_synapse(a.id, b.id, SynapseType.REQUIRES)

    events = await circuit._db.list_events()
    ops = [e["op"] for e in events]
    assert OP_SYNAPSE_RETIRE in ops


@pytest.mark.asyncio
async def test_set_synapse_weight_emits_update(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.REQUIRES, weight=0.3)
    await circuit.set_synapse_weight(a.id, b.id, SynapseType.REQUIRES, 0.8)

    events = await circuit._db.list_events()
    update_events = [e for e in events if e["op"] == OP_SYNAPSE_UPDATE]
    assert len(update_events) == 1
    assert "0.3" in update_events[0]["before_json"]
    assert "0.8" in update_events[0]["after_json"]


@pytest.mark.asyncio
async def test_batched_mutations_share_one_changeset(circuit):
    """Events inside one explicit transaction belong to the same changeset."""
    async with circuit.transaction(actor_id="tester", tag="batch") as tx:
        a = Neuron.create("A")
        b = Neuron.create("B")
        await circuit.add_neuron(a)
        await circuit.add_neuron(b)
        await circuit.add_synapse(a.id, b.id, SynapseType.RELATES_TO)

    events = await circuit._db.list_events(changeset_id=tx.id)
    # 2 neuron.add + 2 synapse.add (bidirectional) = 4 events
    assert len(events) == 4
    ops = [e["op"] for e in events]
    assert ops.count(OP_NEURON_ADD) == 2
    assert ops.count(OP_SYNAPSE_ADD) == 2


@pytest.mark.asyncio
async def test_auto_commit_creates_one_changeset_per_call(circuit):
    """Without an explicit transaction, each mutator opens its own."""
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)

    cur = await circuit._db.conn.execute(
        "SELECT COUNT(*) FROM changeset WHERE status='committed'"
    )
    row = await cur.fetchone()
    assert row[0] == 2
