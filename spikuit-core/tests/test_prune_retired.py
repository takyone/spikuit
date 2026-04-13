"""Tests for Circuit.prune_retired — AMKB v0.7.0 escape hatch."""

from __future__ import annotations

import pytest
import pytest_asyncio

from spikuit_core.circuit import Circuit
from spikuit_core.models import Neuron, SynapseType
from spikuit_core.transactions import OP_NEURON_RETIRE


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "prune.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_prune_deletes_retired_neurons_physically(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    keep = Neuron.create("keep")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_neuron(keep)
    await circuit.add_synapse(a.id, b.id, SynapseType.RELATES_TO)

    await circuit.remove_neuron(a.id)

    # Before prune: retired rows still materially present.
    assert await circuit._db.count_neurons(include_retired=True) == 3

    result = await circuit.prune_retired()
    assert result["neurons_pruned"] == 1
    assert result["synapses_pruned"] >= 1

    # After prune: only the two live neurons remain, even with include_retired.
    assert await circuit._db.count_neurons(include_retired=True) == 2
    assert await circuit._db.get_neuron(a.id, include_retired=True) is None


@pytest.mark.asyncio
async def test_prune_preserves_event_log(circuit):
    a = Neuron.create("A")
    await circuit.add_neuron(a)
    await circuit.remove_neuron(a.id)

    events_before = await circuit._db.list_events()
    assert any(e["op"] == OP_NEURON_RETIRE for e in events_before)

    await circuit.prune_retired()

    events_after = await circuit._db.list_events()
    # Event log count is unchanged: prune does not touch the event table.
    assert len(events_after) == len(events_before)


@pytest.mark.asyncio
async def test_prune_noop_when_no_retired(circuit):
    n = Neuron.create("live")
    await circuit.add_neuron(n)
    result = await circuit.prune_retired()
    assert result == {"neurons_pruned": 0, "synapses_pruned": 0}
    assert await circuit._db.get_neuron(n.id) is not None


@pytest.mark.asyncio
async def test_stats_exposes_retired_count(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.remove_neuron(a.id)

    s = await circuit.stats()
    assert s["neurons"] == 1
    assert s["neurons_retired"] == 1
