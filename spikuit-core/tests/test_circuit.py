"""Tests for Circuit — Neuron/Synapse CRUD and graph operations."""

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Grade, Neuron, Spike, SynapseType


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


SAMPLE_CONTENT = """\
---
type: vocab
domain: language
source: test
---

# functor

圏の間の写像。
"""


# -- Neuron CRUD -----------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get_neuron(circuit):
    neuron = Neuron.create(SAMPLE_CONTENT)
    await circuit.add_neuron(neuron)

    got = await circuit.get_neuron(neuron.id)
    assert got is not None
    assert got.id == neuron.id
    assert got.type == "vocab"
    assert got.domain == "language"
    assert got.source == "test"
    assert "functor" in got.content


@pytest.mark.asyncio
async def test_list_neurons_by_type(circuit):
    n1 = Neuron.create("---\ntype: vocab\n---\n# a")
    n2 = Neuron.create("---\ntype: concept\n---\n# b")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)

    vocabs = await circuit.list_neurons(type="vocab")
    assert len(vocabs) == 1
    assert vocabs[0].id == n1.id


@pytest.mark.asyncio
async def test_update_neuron(circuit):
    neuron = Neuron.create(SAMPLE_CONTENT)
    await circuit.add_neuron(neuron)

    neuron.content = neuron.content.replace("functor", "monad")
    neuron.type = "concept"
    await circuit.update_neuron(neuron)

    got = await circuit.get_neuron(neuron.id)
    assert "monad" in got.content
    assert got.type == "concept"


@pytest.mark.asyncio
async def test_remove_neuron(circuit):
    neuron = Neuron.create(SAMPLE_CONTENT)
    await circuit.add_neuron(neuron)
    await circuit.remove_neuron(neuron.id)

    assert await circuit.get_neuron(neuron.id) is None
    assert circuit.neuron_count == 0


# -- Synapse CRUD ----------------------------------------------------------


@pytest.mark.asyncio
async def test_add_directed_synapse(circuit):
    n1 = Neuron.create("---\ntype: vocab\n---\n# A")
    n2 = Neuron.create("---\ntype: vocab\n---\n# B")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)

    created = await circuit.add_synapse(n1.id, n2.id, SynapseType.REQUIRES)
    assert len(created) == 1
    assert circuit.synapse_count == 1

    # Direction: n1 -> n2
    assert n2.id in circuit.neighbors(n1.id)
    assert n1.id not in circuit.neighbors(n2.id)


@pytest.mark.asyncio
async def test_add_bidirectional_synapse(circuit):
    n1 = Neuron.create("---\ntype: vocab\n---\n# A")
    n2 = Neuron.create("---\ntype: vocab\n---\n# B")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)

    created = await circuit.add_synapse(n1.id, n2.id, SynapseType.CONTRASTS)
    assert len(created) == 2
    assert circuit.synapse_count == 2

    # Both directions
    assert n2.id in circuit.neighbors(n1.id)
    assert n1.id in circuit.neighbors(n2.id)


@pytest.mark.asyncio
async def test_remove_bidirectional_synapse(circuit):
    n1 = Neuron.create("---\ntype: vocab\n---\n# A")
    n2 = Neuron.create("---\ntype: vocab\n---\n# B")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)

    await circuit.add_synapse(n1.id, n2.id, SynapseType.CONTRASTS)
    await circuit.remove_synapse(n1.id, n2.id, SynapseType.CONTRASTS)
    assert circuit.synapse_count == 0


@pytest.mark.asyncio
async def test_synapse_requires_existing_neurons(circuit):
    with pytest.raises(ValueError, match="Both neurons must exist"):
        await circuit.add_synapse("fake-1", "fake-2", SynapseType.RELATES_TO)


# -- Spike (fire) -----------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_records_spike(circuit):
    neuron = Neuron.create(SAMPLE_CONTENT)
    await circuit.add_neuron(neuron)

    spike = Spike(neuron_id=neuron.id, grade=Grade.FIRE)
    await circuit.fire(spike)

    spikes = await circuit._db.get_spikes_for(neuron.id)
    assert len(spikes) == 1
    assert spikes[0].grade == Grade.FIRE


# -- Ensemble ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensemble(circuit):
    # Create a chain: A -> B -> C
    na = Neuron.create("# A")
    nb = Neuron.create("# B")
    nc = Neuron.create("# C")
    nd = Neuron.create("# D (isolated)")
    for n in [na, nb, nc, nd]:
        await circuit.add_neuron(n)

    await circuit.add_synapse(na.id, nb.id, SynapseType.REQUIRES)
    await circuit.add_synapse(nb.id, nc.id, SynapseType.REQUIRES)

    # 1-hop from A: only B
    e1 = circuit.ensemble(na.id, hops=1)
    assert nb.id in e1
    assert nc.id not in e1

    # 2-hop from A: B and C
    e2 = circuit.ensemble(na.id, hops=2)
    assert nb.id in e2
    assert nc.id in e2
    assert nd.id not in e2  # isolated


# -- Retrieve ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_keyword(circuit):
    n1 = Neuron.create("# msgspec\n\nC拡張の高速シリアライザ")
    n2 = Neuron.create("# Pydantic\n\nバリデーション重視のライブラリ")
    n3 = Neuron.create("# functor\n\n圏の間の写像")
    for n in [n1, n2, n3]:
        await circuit.add_neuron(n)

    results = await circuit.retrieve("msgspec")
    assert len(results) == 1
    assert results[0].id == n1.id


@pytest.mark.asyncio
async def test_retrieve_logs(circuit):
    n1 = Neuron.create("# test neuron\n\ncontent here")
    await circuit.add_neuron(n1)

    await circuit.retrieve("test")

    # Check log was written
    rows = await circuit._db.conn.execute_fetchall("SELECT * FROM retrieve_log")
    assert len(rows) == 1
    assert rows[0]["query"] == "test"


# -- Stats ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats(circuit):
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse(n1.id, n2.id, SynapseType.RELATES_TO)

    s = await circuit.stats()
    assert s["neurons"] == 2
    assert s["synapses"] == 2  # bidirectional


# -- Graph reload -----------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_reload(tmp_path):
    """Graph should be fully reconstructed from DB on connect."""
    db_path = tmp_path / "reload.db"

    # First session: create data
    c1 = Circuit(db_path=db_path)
    await c1.connect()
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await c1.add_neuron(n1)
    await c1.add_neuron(n2)
    await c1.add_synapse(n1.id, n2.id, SynapseType.EXTENDS)
    await c1.close()

    # Second session: reload
    c2 = Circuit(db_path=db_path)
    await c2.connect()
    assert c2.neuron_count == 2
    assert c2.synapse_count == 1
    assert n2.id in c2.neighbors(n1.id)
    await c2.close()
