"""Tests for Step 3: STDP edge weight updates + co-fire tracking.

TDD — tests written before implementation.
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


async def _make_pair(
    circuit: Circuit,
) -> tuple[Neuron, Neuron]:
    """Create A --requires--> B."""
    a = Neuron.create("# A\n\nConcept A")
    b = Neuron.create("# B\n\nConcept B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    await circuit.add_synapse(a.id, b.id, SynapseType.REQUIRES)
    return a, b


# -------------------------------------------------------------------
# STDP basics
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co_fire_increments_on_nearby_spikes(circuit: Circuit):
    """When A fires then B fires within tau_stdp, co_fires on A→B increments."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    # B fires 1 day later — within tau_stdp (7 days)
    await circuit.fire(
        Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=now + timedelta(days=1))
    )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    assert syn.co_fires >= 1


@pytest.mark.asyncio
async def test_no_co_fire_beyond_tau_stdp(circuit: Circuit):
    """Spikes separated by more than tau_stdp should NOT count as co-fire."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    # B fires 10 days later — beyond tau_stdp (7 days)
    await circuit.fire(
        Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=now + timedelta(days=10))
    )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    assert syn.co_fires == 0


@pytest.mark.asyncio
async def test_stdp_ltp_strengthens_edge(circuit: Circuit):
    """Pre fires before post (within tau_stdp) → LTP → weight increases."""
    a, b = await _make_pair(circuit)
    initial_weight = 0.5
    now = datetime.now(timezone.utc)

    # A (pre) fires first
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    # B (post) fires 1 day later
    await circuit.fire(
        Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=now + timedelta(days=1))
    )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    assert syn.weight > initial_weight


@pytest.mark.asyncio
async def test_stdp_ltd_weakens_edge(circuit: Circuit):
    """Post fires before pre (within tau_stdp) → LTD → weight decreases."""
    a, b = await _make_pair(circuit)
    initial_weight = 0.5
    now = datetime.now(timezone.utc)

    # B (post) fires first
    await circuit.fire(Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=now))
    # A (pre) fires 1 day later — post fired before pre → LTD
    await circuit.fire(
        Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now + timedelta(days=1))
    )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    assert syn.weight < initial_weight


@pytest.mark.asyncio
async def test_stdp_decay_with_time_difference(tmp_path):
    """STDP effect should be stronger for closer spikes."""
    now = datetime.now(timezone.utc)

    # Pair 1: fire 1 day apart (stronger STDP)
    c1 = Circuit(db_path=tmp_path / "close.db")
    await c1.connect()
    a1, b1 = await _make_pair(c1)
    await c1.fire(Spike(neuron_id=a1.id, grade=Grade.FIRE, fired_at=now))
    await c1.fire(
        Spike(neuron_id=b1.id, grade=Grade.FIRE, fired_at=now + timedelta(days=1))
    )

    # Pair 2: fire 5 days apart (weaker STDP)
    c2 = Circuit(db_path=tmp_path / "far.db")
    await c2.connect()
    a2, b2 = await _make_pair(c2)
    await c2.fire(Spike(neuron_id=a2.id, grade=Grade.FIRE, fired_at=now))
    await c2.fire(
        Spike(neuron_id=b2.id, grade=Grade.FIRE, fired_at=now + timedelta(days=5))
    )

    syn1 = await c1.get_synapse(a1.id, b1.id, SynapseType.REQUIRES)
    syn2 = await c2.get_synapse(a2.id, b2.id, SynapseType.REQUIRES)
    assert syn1 is not None and syn2 is not None
    # Closer spikes → bigger weight change
    assert syn1.weight > syn2.weight

    await c1.close()
    await c2.close()


# -------------------------------------------------------------------
# Weight bounds
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weight_clamp_ceiling(circuit: Circuit):
    """Weight should never exceed weight_ceiling."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    # Repeatedly fire in LTP pattern to push weight up
    for i in range(50):
        t = now + timedelta(hours=i * 2)
        await circuit.fire(Spike(neuron_id=a.id, grade=Grade.STRONG, fired_at=t))
        await circuit.fire(
            Spike(
                neuron_id=b.id,
                grade=Grade.STRONG,
                fired_at=t + timedelta(hours=1),
            )
        )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    assert syn.weight <= circuit.plasticity.weight_ceiling


@pytest.mark.asyncio
async def test_weight_clamp_floor(circuit: Circuit):
    """Weight should never go below weight_floor."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    # Repeatedly fire in LTD pattern to push weight down
    for i in range(50):
        t = now + timedelta(hours=i * 2)
        # B (post) fires first → LTD
        await circuit.fire(Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=t))
        await circuit.fire(
            Spike(
                neuron_id=a.id,
                grade=Grade.FIRE,
                fired_at=t + timedelta(hours=1),
            )
        )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    assert syn.weight >= circuit.plasticity.weight_floor


# -------------------------------------------------------------------
# Synapse persistence
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdp_changes_persist_to_db(circuit: Circuit):
    """STDP weight changes and co_fires should be saved to the database."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    await circuit.fire(
        Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=now + timedelta(days=1))
    )

    # Read from DB directly
    syn_db = await circuit._db.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn_db is not None
    assert syn_db.weight != 0.5  # Changed from initial
    assert syn_db.co_fires >= 1
    assert syn_db.last_co_fire is not None


# -------------------------------------------------------------------
# Graph in-memory sync
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdp_updates_graph_edge(circuit: Circuit):
    """STDP changes should also update the in-memory NetworkX graph."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    await circuit.fire(
        Spike(neuron_id=b.id, grade=Grade.FIRE, fired_at=now + timedelta(days=1))
    )

    edge_data = circuit.graph[a.id][b.id]
    assert edge_data["weight"] != 0.5
    assert edge_data["co_fires"] >= 1


# -------------------------------------------------------------------
# MISS grade — no co-fire
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_miss_grade_no_co_fire(circuit: Circuit):
    """MISS grade should not trigger co-fire or LTP."""
    a, b = await _make_pair(circuit)
    now = datetime.now(timezone.utc)

    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    # B fires MISS — failed review should not strengthen
    await circuit.fire(
        Spike(neuron_id=b.id, grade=Grade.MISS, fired_at=now + timedelta(days=1))
    )

    syn = await circuit.get_synapse(a.id, b.id, SynapseType.REQUIRES)
    assert syn is not None
    # MISS should not count as a positive co-fire
    assert syn.co_fires == 0
    # Weight should not have increased
    assert syn.weight <= 0.5
