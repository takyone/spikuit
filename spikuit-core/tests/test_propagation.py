"""Tests for Step 2: LIF pressure model + APPNP propagation.

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


async def _make_chain(circuit: Circuit) -> tuple[Neuron, Neuron, Neuron]:
    """Create A --requires--> B --requires--> C."""
    a = Neuron.create("# A\n\nConcept A")
    b = Neuron.create("# B\n\nConcept B")
    c = Neuron.create("# C\n\nConcept C")
    for n in [a, b, c]:
        await circuit.add_neuron(n)
    await circuit.add_synapse(a.id, b.id, SynapseType.REQUIRES)
    await circuit.add_synapse(b.id, c.id, SynapseType.REQUIRES)
    return a, b, c


async def _make_star(circuit: Circuit) -> tuple[Neuron, list[Neuron]]:
    """Create hub H with 4 spokes S1..S4 (H --relates_to--> each S)."""
    hub = Neuron.create("# Hub")
    spokes = [Neuron.create(f"# Spoke {i}") for i in range(4)]
    await circuit.add_neuron(hub)
    for s in spokes:
        await circuit.add_neuron(s)
        await circuit.add_synapse(hub.id, s.id, SynapseType.RELATES_TO)
    return hub, spokes


# -- Pressure initialization ------------------------------------------------


@pytest.mark.asyncio
async def test_initial_pressure_is_zero(circuit: Circuit):
    """Newly added neurons should have zero pressure."""
    n = Neuron.create("# test")
    await circuit.add_neuron(n)

    pressure = circuit.get_pressure(n.id)
    assert pressure == 0.0


# -- Fire propagates pressure to neighbors ----------------------------------


@pytest.mark.asyncio
async def test_fire_increases_neighbor_pressure(circuit: Circuit):
    """Firing neuron A should increase pressure on its neighbor B."""
    a, b, c = await _make_chain(circuit)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))

    assert circuit.get_pressure(b.id) > 0.0


@pytest.mark.asyncio
async def test_fire_does_not_increase_own_pressure(circuit: Circuit):
    """Firing a neuron should reset its own pressure (post-fire reset)."""
    a, b, c = await _make_chain(circuit)

    # Give A some pressure first
    circuit._set_pressure(a.id, 0.5)
    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))

    # After firing, pressure should be reset to pressure_reset
    assert circuit.get_pressure(a.id) == circuit.plasticity.pressure_reset


@pytest.mark.asyncio
async def test_propagation_decays_with_distance(circuit: Circuit):
    """Pressure should decrease with graph distance from the fired neuron."""
    a, b, c = await _make_chain(circuit)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))

    p_b = circuit.get_pressure(b.id)
    p_c = circuit.get_pressure(c.id)

    assert p_b > p_c > 0.0


@pytest.mark.asyncio
async def test_isolated_neuron_no_propagation(circuit: Circuit):
    """An isolated neuron's fire should not affect any other neuron."""
    a = Neuron.create("# isolated A")
    b = Neuron.create("# isolated B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)
    # No synapse between them

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))

    assert circuit.get_pressure(b.id) == 0.0


# -- Fan effect (hub nodes distribute activation) ---------------------------


@pytest.mark.asyncio
async def test_fan_effect_distributes_activation(circuit: Circuit):
    """A hub with many connections should distribute activation thinly."""
    hub, spokes = await _make_star(circuit)

    # Also create a simple pair for comparison
    x = Neuron.create("# X")
    y = Neuron.create("# Y")
    await circuit.add_neuron(x)
    await circuit.add_neuron(y)
    await circuit.add_synapse(x.id, y.id, SynapseType.RELATES_TO)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=hub.id, grade=Grade.FIRE, fired_at=now))
    await circuit.fire(Spike(neuron_id=x.id, grade=Grade.FIRE, fired_at=now))

    # Each spoke should get less pressure than Y (single connection)
    spoke_pressure = circuit.get_pressure(spokes[0].id)
    y_pressure = circuit.get_pressure(y.id)
    assert y_pressure > spoke_pressure


# -- Grade affects propagation strength -------------------------------------


@pytest.mark.asyncio
async def test_miss_grade_no_positive_propagation(circuit: Circuit):
    """Grade.MISS should not propagate positive pressure to neighbors."""
    a, b, c = await _make_chain(circuit)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.MISS, fired_at=now))

    # MISS = failed review, should not activate neighbors positively
    assert circuit.get_pressure(b.id) <= 0.0


@pytest.mark.asyncio
async def test_strong_grade_propagates_more(circuit: Circuit):
    """Grade.STRONG should propagate more pressure than Grade.FIRE."""
    # Two identical chains
    a1 = Neuron.create("# A1")
    b1 = Neuron.create("# B1")
    a2 = Neuron.create("# A2")
    b2 = Neuron.create("# B2")
    for n in [a1, b1, a2, b2]:
        await circuit.add_neuron(n)
    await circuit.add_synapse(a1.id, b1.id, SynapseType.REQUIRES)
    await circuit.add_synapse(a2.id, b2.id, SynapseType.REQUIRES)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a1.id, grade=Grade.FIRE, fired_at=now))
    await circuit.fire(Spike(neuron_id=a2.id, grade=Grade.STRONG, fired_at=now))

    assert circuit.get_pressure(b2.id) > circuit.get_pressure(b1.id)


# -- Pressure accumulation -------------------------------------------------


@pytest.mark.asyncio
async def test_pressure_accumulates_from_multiple_neighbors(circuit: Circuit):
    """Pressure from multiple neighbors should accumulate."""
    # B <-- A1, B <-- A2
    a1 = Neuron.create("# A1")
    a2 = Neuron.create("# A2")
    b = Neuron.create("# B")
    for n in [a1, a2, b]:
        await circuit.add_neuron(n)
    await circuit.add_synapse(a1.id, b.id, SynapseType.RELATES_TO)
    await circuit.add_synapse(a2.id, b.id, SynapseType.RELATES_TO)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a1.id, grade=Grade.FIRE, fired_at=now))
    p_after_one = circuit.get_pressure(b.id)

    await circuit.fire(Spike(neuron_id=a2.id, grade=Grade.FIRE, fired_at=now))
    p_after_two = circuit.get_pressure(b.id)

    assert p_after_two > p_after_one


# -- Pressure decay over time (LIF leak) ------------------------------------


@pytest.mark.asyncio
async def test_pressure_decays_over_time(circuit: Circuit):
    """Pressure should decay when time passes (leaky integrate)."""
    a, b, c = await _make_chain(circuit)

    now = datetime.now(timezone.utc)
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))
    p_initial = circuit.get_pressure(b.id)

    # Simulate time passing by decaying pressure
    future = now + timedelta(days=7)
    circuit.decay_pressure(now=future)
    p_decayed = circuit.get_pressure(b.id)

    assert 0.0 < p_decayed < p_initial


# -- APPNP convergence properties ------------------------------------------


@pytest.mark.asyncio
async def test_propagation_handles_cycles(circuit: Circuit):
    """APPNP should converge even with cycles in the graph."""
    # A -> B -> C -> A (cycle)
    a = Neuron.create("# A")
    b = Neuron.create("# B")
    c = Neuron.create("# C")
    for n in [a, b, c]:
        await circuit.add_neuron(n)
    await circuit.add_synapse(a.id, b.id, SynapseType.REQUIRES)
    await circuit.add_synapse(b.id, c.id, SynapseType.REQUIRES)
    await circuit.add_synapse(c.id, a.id, SynapseType.REQUIRES)

    now = datetime.now(timezone.utc)
    # Should not hang or crash
    await circuit.fire(Spike(neuron_id=a.id, grade=Grade.FIRE, fired_at=now))

    # All nodes should have finite, non-negative pressure
    for n in [a, b, c]:
        p = circuit.get_pressure(n.id)
        assert 0.0 <= p < float("inf")


# -- Plasticity configuration -----------------------------------------------


@pytest.mark.asyncio
async def test_custom_plasticity_affects_propagation(tmp_path):
    """Different alpha values should change propagation locality."""
    # Local propagation (high alpha = more teleport = less spread)
    c_local = Circuit(
        db_path=tmp_path / "local.db",
        plasticity=Plasticity(alpha=0.5),
    )
    await c_local.connect()
    a1, b1, c1 = await _make_chain(c_local)

    # Global propagation (low alpha = less teleport = more spread)
    c_global = Circuit(
        db_path=tmp_path / "global.db",
        plasticity=Plasticity(alpha=0.05),
    )
    await c_global.connect()
    a2, b2, c2 = await _make_chain(c_global)

    now = datetime.now(timezone.utc)
    await c_local.fire(Spike(neuron_id=a1.id, grade=Grade.FIRE, fired_at=now))
    await c_global.fire(Spike(neuron_id=a2.id, grade=Grade.FIRE, fired_at=now))

    # With higher alpha, far nodes get less pressure
    p_c_local = c_local.get_pressure(c1.id)
    p_c_global = c_global.get_pressure(c2.id)
    assert p_c_global > p_c_local

    await c_local.close()
    await c_global.close()
