"""Hot-path cost containment for Circuit.fire() — AMKB v0.7.0.

The AMKB integration spec §5 explicitly excludes ``fire()`` from event
emission to keep the spaced-repetition hot path free of write
amplification. These tests lock in that invariant and provide a rough
timing budget so future refactors can notice regressions.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

from spikuit_core.circuit import Circuit
from spikuit_core.models import Grade, Neuron, Spike, SynapseType


@pytest_asyncio.fixture
async def populated_circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "fire_perf.db")
    await c.connect()
    neurons = [Neuron.create(f"# N{i}\n\ncontent {i}") for i in range(20)]
    for n in neurons:
        await c.add_neuron(n)
    # Light connectivity: each neuron links to the next two.
    for i in range(20):
        for k in (1, 2):
            j = (i + k) % 20
            await c.add_synapse(
                neurons[i].id, neurons[j].id, SynapseType.RELATES_TO,
            )
    yield c, neurons
    await c.close()


@pytest.mark.asyncio
async def test_fire_emits_no_events_or_changesets(populated_circuit):
    """AMKB v0.7.0 spec §5: fire() must not write to event or changeset."""
    c, neurons = populated_circuit

    events_before = len(await c._db.list_events())
    cur = await c._db.conn.execute("SELECT COUNT(*) FROM changeset")
    cs_before = (await cur.fetchone())[0]

    for n in neurons[:5]:
        await c.fire(Spike(neuron_id=n.id, grade=Grade.FIRE))

    events_after = len(await c._db.list_events())
    cur = await c._db.conn.execute("SELECT COUNT(*) FROM changeset")
    cs_after = (await cur.fetchone())[0]

    assert events_after == events_before, (
        "fire() leaked into the AMKB event log — hot path write amplification"
    )
    assert cs_after == cs_before, (
        "fire() opened a changeset — hot path should bypass the tx wrapper"
    )


@pytest.mark.asyncio
async def test_fire_timing_budget(populated_circuit):
    """Sanity budget: 50 fires should finish comfortably under 5s.

    This is not a tight microbenchmark — it's a coarse tripwire that
    fails if a future change makes fire() dramatically slower (e.g. by
    accidentally wiring it through the event-log code path).
    """
    c, neurons = populated_circuit

    start = time.perf_counter()
    for i in range(50):
        n = neurons[i % len(neurons)]
        await c.fire(Spike(neuron_id=n.id, grade=Grade.FIRE))
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"fire() budget blown: 50 fires took {elapsed:.2f}s"
