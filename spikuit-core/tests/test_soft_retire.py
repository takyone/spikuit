"""Tests for soft-retire behavior — AMKB v0.7.0 plumbing."""

from __future__ import annotations

import pytest
import pytest_asyncio

from spikuit_core.circuit import Circuit
from spikuit_core.models import Neuron, SynapseType
from spikuit_core.transactions import OP_NEURON_RETIRE, OP_SYNAPSE_RETIRE


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "retire.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_retire_hides_from_list_and_get(circuit):
    n = Neuron.create("# Functor\n\nA mapping between categories.")
    await circuit.add_neuron(n)

    assert await circuit.get_neuron(n.id) is not None
    assert len(await circuit.list_neurons()) == 1

    await circuit.remove_neuron(n.id)

    assert await circuit.get_neuron(n.id) is None
    assert await circuit.list_neurons() == []
    assert await circuit._db.count_neurons() == 0


@pytest.mark.asyncio
async def test_retired_row_still_exists_in_db(circuit):
    n = Neuron.create("content")
    await circuit.add_neuron(n)
    await circuit.remove_neuron(n.id)

    # The row is preserved with retired_at set — visible via include_retired.
    row = await circuit._db.get_neuron(n.id, include_retired=True)
    assert row is not None
    assert row.id == n.id

    raw = await circuit._db.conn.execute_fetchall(
        "SELECT retired_at FROM neuron WHERE id=?", (n.id,)
    )
    assert raw[0]["retired_at"] is not None


@pytest.mark.asyncio
async def test_retire_cascades_synapses(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.RELATES_TO)
    await circuit.add_synapse(b.id, a.id, SynapseType.RELATES_TO)

    assert len(await circuit._db.get_all_synapses()) == 2

    await circuit.remove_neuron(a.id)

    # Both synapses cascade-retired.
    assert await circuit._db.get_all_synapses() == []
    # But still recoverable via include_retired.
    all_retired = await circuit._db.get_all_synapses(include_retired=True)
    assert len(all_retired) == 2


@pytest.mark.asyncio
async def test_retire_emits_events(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.RELATES_TO)

    await circuit.remove_neuron(a.id)

    events = await circuit._db.list_events(target_id=a.id)
    assert any(e["op"] == OP_NEURON_RETIRE for e in events)
    all_events = await circuit._db.list_events()
    ops = [e["op"] for e in all_events]
    assert OP_NEURON_RETIRE in ops
    assert OP_SYNAPSE_RETIRE in ops


@pytest.mark.asyncio
async def test_retire_idempotent(circuit):
    n = Neuron.create("x")
    await circuit.add_neuron(n)
    await circuit.remove_neuron(n.id)
    # Second call is a no-op.
    await circuit.remove_neuron(n.id)
    # And on a completely unknown id.
    await circuit.remove_neuron("n-does-not-exist")


@pytest.mark.asyncio
async def test_retired_neuron_absent_from_graph(circuit):
    n = Neuron.create("x")
    await circuit.add_neuron(n)
    assert n.id in circuit._graph
    await circuit.remove_neuron(n.id)
    assert n.id not in circuit._graph


@pytest.mark.asyncio
async def test_retire_inside_explicit_transaction(circuit):
    n = Neuron.create("x")
    await circuit.add_neuron(n)

    async with circuit.transaction(
        actor_id="tester", tag="batch-cleanup",
    ) as tx:
        await circuit.remove_neuron(n.id)
        # Events belong to the caller's changeset, not an implicit one.
        events = [(e.op, e.target_kind) for e in tx.events]
        assert (OP_NEURON_RETIRE, "neuron") in events

    row = await circuit._db.get_changeset(tx.id)
    assert row["status"] == "committed"
    assert row["tag"] == "batch-cleanup"


@pytest.mark.asyncio
async def test_circuit_get_neuron_include_retired(circuit):
    n = Neuron.create("x")
    await circuit.add_neuron(n)
    await circuit.remove_neuron(n.id)

    # Default path hides the retired neuron.
    assert await circuit.get_neuron(n.id) is None
    # Adapter-facing path resolves retired references.
    resolved = await circuit.get_neuron(n.id, include_retired=True)
    assert resolved is not None
    assert resolved.id == n.id


@pytest.mark.asyncio
async def test_circuit_get_synapse_include_retired(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.RELATES_TO)

    await circuit.remove_neuron(a.id)  # cascade-retires the synapse

    assert await circuit.get_synapse(
        a.id, b.id, SynapseType.RELATES_TO,
    ) is None
    resolved = await circuit.get_synapse(
        a.id, b.id, SynapseType.RELATES_TO, include_retired=True,
    )
    assert resolved is not None
    assert resolved.pre == a.id and resolved.post == b.id
