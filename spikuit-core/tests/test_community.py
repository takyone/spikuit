"""Tests for community detection and persistence."""

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Neuron, SynapseType


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


def _make_cluster(prefix: str, size: int) -> list[Neuron]:
    return [Neuron.create(f"# {prefix}-{i}") for i in range(size)]


@pytest.mark.asyncio
async def test_detect_communities_empty_graph(circuit):
    result = await circuit.detect_communities()
    assert result == {}


@pytest.mark.asyncio
async def test_detect_communities_single_node(circuit):
    n = Neuron.create("# Solo")
    await circuit.add_neuron(n)

    result = await circuit.detect_communities()
    assert len(result) == 1
    assert n.id in result[0]


@pytest.mark.asyncio
async def test_detect_communities_two_clusters(circuit):
    """Two densely connected clusters with a single bridge should yield 2 communities."""
    # Cluster A: 4 nodes, fully connected
    a = _make_cluster("A", 4)
    for n in a:
        await circuit.add_neuron(n)
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            await circuit.add_synapse(a[i].id, a[j].id, SynapseType.RELATES_TO)

    # Cluster B: 4 nodes, fully connected
    b = _make_cluster("B", 4)
    for n in b:
        await circuit.add_neuron(n)
    for i in range(len(b)):
        for j in range(i + 1, len(b)):
            await circuit.add_synapse(b[i].id, b[j].id, SynapseType.RELATES_TO)

    # Single bridge between clusters
    await circuit.add_synapse(a[0].id, b[0].id, SynapseType.RELATES_TO)

    result = await circuit.detect_communities()
    assert len(result) >= 2

    # Each cluster's nodes should be in the same community
    a_ids = {n.id for n in a}
    b_ids = {n.id for n in b}

    a_communities = {circuit.get_community(nid) for nid in a_ids}
    b_communities = {circuit.get_community(nid) for nid in b_ids}

    # All of cluster A in one community, all of cluster B in another
    assert len(a_communities) == 1
    assert len(b_communities) == 1
    assert a_communities != b_communities


@pytest.mark.asyncio
async def test_community_map(circuit):
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse(n1.id, n2.id, SynapseType.RELATES_TO)

    await circuit.detect_communities()

    cmap = circuit.community_map()
    assert n1.id in cmap
    assert n2.id in cmap


@pytest.mark.asyncio
async def test_get_community_unknown_node(circuit):
    assert circuit.get_community("nonexistent") is None


@pytest.mark.asyncio
async def test_community_persists_across_reload(tmp_path):
    """Community IDs should survive Circuit reconnection."""
    db_path = tmp_path / "community.db"

    c1 = Circuit(db_path=db_path)
    await c1.connect()
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await c1.add_neuron(n1)
    await c1.add_neuron(n2)
    await c1.add_synapse(n1.id, n2.id, SynapseType.RELATES_TO)
    await c1.detect_communities()
    original_map = c1.community_map()
    await c1.close()

    c2 = Circuit(db_path=db_path)
    await c2.connect()
    reloaded_map = c2.community_map()
    assert reloaded_map == original_map
    await c2.close()


@pytest.mark.asyncio
async def test_stats_includes_communities(circuit):
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse(n1.id, n2.id, SynapseType.RELATES_TO)
    await circuit.detect_communities()

    s = await circuit.stats()
    assert "communities" in s
    assert s["communities"] >= 1


@pytest.mark.asyncio
async def test_detect_communities_resolution(circuit):
    """Higher resolution should produce more (or equal) communities."""
    nodes = _make_cluster("N", 6)
    for n in nodes:
        await circuit.add_neuron(n)
    # Chain: 0-1-2-3-4-5
    for i in range(len(nodes) - 1):
        await circuit.add_synapse(
            nodes[i].id, nodes[i + 1].id, SynapseType.RELATES_TO
        )

    low = await circuit.detect_communities(resolution=0.5)
    high = await circuit.detect_communities(resolution=3.0)
    assert len(high) >= len(low)
