"""Tests for Step 4: Graph-weighted retrieve scoring.

TDD — tests written before implementation.
Retrieve score = keyword_match × retrievability × stability_norm × centrality × pressure_boost
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Grade, Neuron, Plasticity, Spike, SynapseType


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


# -------------------------------------------------------------------
# Basic keyword retrieve (existing behavior preserved)
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_matching_neurons(circuit: Circuit):
    """Basic keyword matching still works."""
    n1 = Neuron.create("# Functor\n\nA mapping between categories.")
    n2 = Neuron.create("# Monad\n\nA monoid in the category of endofunctors.")
    n3 = Neuron.create("# Banana\n\nA yellow fruit.")
    for n in [n1, n2, n3]:
        await circuit.add_neuron(n)

    results = await circuit.retrieve("functor")
    ids = [r.id for r in results]
    assert n1.id in ids
    # n2 mentions "endofunctors" which contains "functor"
    assert n2.id in ids
    assert n3.id not in ids


@pytest.mark.asyncio
async def test_retrieve_empty_query_returns_nothing(circuit: Circuit):
    """Empty query should return no results."""
    n1 = Neuron.create("# Something")
    await circuit.add_neuron(n1)
    results = await circuit.retrieve("")
    assert len(results) == 0


# -------------------------------------------------------------------
# FSRS retrievability boosts recently reviewed neurons
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recently_reviewed_ranks_higher(circuit: Circuit):
    """A recently reviewed neuron should rank higher than a stale one."""
    n_reviewed = Neuron.create("# Category Theory\n\nStudy of abstract structures.")
    n_stale = Neuron.create("# Category Theory basics\n\nIntro to categories.")
    await circuit.add_neuron(n_reviewed)
    await circuit.add_neuron(n_stale)

    # Review n_reviewed multiple times to build retrievability
    now = datetime.now(timezone.utc)
    for i in range(3):
        t = now + timedelta(days=i)
        await circuit.fire(
            Spike(neuron_id=n_reviewed.id, grade=Grade.FIRE, fired_at=t)
        )

    results = await circuit.retrieve("category theory")
    assert len(results) >= 2
    # Reviewed neuron should come first
    assert results[0].id == n_reviewed.id


# -------------------------------------------------------------------
# Graph centrality boosts well-connected neurons
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_well_connected_ranks_higher(circuit: Circuit):
    """A neuron with more connections should rank higher (all else equal)."""
    # Hub: connected to many
    hub = Neuron.create("# Linear Algebra\n\nThe study of linear maps.")
    spoke1 = Neuron.create("# Matrix\n\nA rectangular array.")
    spoke2 = Neuron.create("# Vector\n\nAn element of a vector space.")
    spoke3 = Neuron.create("# Eigenvalue\n\nA scalar in linear algebra.")
    # Isolated: same content relevance but no connections
    isolated = Neuron.create("# Linear Algebra intro\n\nBasics of linear algebra.")

    for n in [hub, spoke1, spoke2, spoke3, isolated]:
        await circuit.add_neuron(n)

    await circuit.add_synapse(hub.id, spoke1.id, SynapseType.REQUIRES)
    await circuit.add_synapse(hub.id, spoke2.id, SynapseType.REQUIRES)
    await circuit.add_synapse(hub.id, spoke3.id, SynapseType.REQUIRES)

    results = await circuit.retrieve("linear algebra")
    assert len(results) >= 2
    ids = [r.id for r in results]
    # Hub should rank higher than isolated due to centrality
    assert ids.index(hub.id) < ids.index(isolated.id)


# -------------------------------------------------------------------
# Pressure boost surfaces "about to fire" neurons
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pressure_boosts_retrieve_rank(circuit: Circuit):
    """Neurons with high pressure should rank higher."""
    n_pressure = Neuron.create("# Topology\n\nStudy of geometric properties.")
    n_no_pressure = Neuron.create("# Topology basics\n\nIntro to topology.")
    await circuit.add_neuron(n_pressure)
    await circuit.add_neuron(n_no_pressure)

    # Give one neuron high pressure
    circuit._set_pressure(n_pressure.id, 0.7)

    results = await circuit.retrieve("topology")
    assert len(results) >= 2
    assert results[0].id == n_pressure.id


# -------------------------------------------------------------------
# Limit and edge cases
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_respects_limit(circuit: Circuit):
    """Should return at most `limit` results."""
    for i in range(20):
        await circuit.add_neuron(Neuron.create(f"# Topic {i}\n\nAbout topic."))

    results = await circuit.retrieve("topic", limit=5)
    assert len(results) <= 5


@pytest.mark.asyncio
async def test_retrieve_no_matches(circuit: Circuit):
    """Query with no matches returns empty list."""
    await circuit.add_neuron(Neuron.create("# Apple\n\nA fruit."))
    results = await circuit.retrieve("quantum physics")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_retrieve_logs_query(circuit: Circuit):
    """Retrieve should log the query and results for future analysis."""
    n1 = Neuron.create("# Test\n\nA test neuron.")
    await circuit.add_neuron(n1)

    await circuit.retrieve("test")

    # Check that the retrieve was logged
    rows = await circuit._db.conn.execute_fetchall(
        "SELECT * FROM retrieve_log"
    )
    assert len(rows) >= 1
    assert rows[0]["query"] == "test"
