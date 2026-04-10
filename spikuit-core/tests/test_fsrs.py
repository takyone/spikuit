"""Tests for Step 1: FSRS integration in Circuit.

TDD — these tests are written BEFORE the implementation is complete.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fsrs import Card

from spikuit_core import Circuit, Grade, Neuron, Spike


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


@pytest_asyncio.fixture
async def neuron_in_circuit(circuit: Circuit) -> Neuron:
    """A neuron already added to the circuit."""
    n = Neuron.create("---\ntype: vocab\n---\n# test item\n\nsome content")
    await circuit.add_neuron(n)
    return n


# -- FSRS Card initialization -----------------------------------------------


@pytest.mark.asyncio
async def test_add_neuron_creates_fsrs_card(circuit: Circuit):
    """Adding a neuron should auto-create an FSRS Card."""
    n = Neuron.create("# test")
    await circuit.add_neuron(n)

    card = circuit.get_card(n.id)
    assert card is not None
    assert isinstance(card, Card)


@pytest.mark.asyncio
async def test_initial_card_is_due_immediately(circuit: Circuit):
    """A newly added neuron should be due for review immediately."""
    n = Neuron.create("# test")
    await circuit.add_neuron(n)

    now = datetime.now(timezone.utc)
    due = await circuit.due_neurons(now=now)
    assert n.id in due


# -- Fire updates FSRS state ------------------------------------------------


@pytest.mark.asyncio
async def test_fire_updates_fsrs_stability(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """Firing a spike should update the FSRS card's stability."""
    card_before = circuit.get_card(neuron_in_circuit.id)
    assert card_before is not None

    spike = Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE)
    updated_card = await circuit.fire(spike)

    assert updated_card.stability is not None
    assert updated_card.stability > 0


@pytest.mark.asyncio
async def test_fire_updates_fsrs_difficulty(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """Firing a spike should set difficulty on the FSRS card."""
    spike = Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE)
    updated_card = await circuit.fire(spike)

    assert updated_card.difficulty is not None
    assert updated_card.difficulty > 0


@pytest.mark.asyncio
async def test_fire_schedules_next_review(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """After firing, the card's due date should be in the future."""
    spike = Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE)
    updated_card = await circuit.fire(spike)

    # Due should be after the spike time
    assert updated_card.due > spike.fired_at


@pytest.mark.asyncio
async def test_fire_returns_updated_card(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """fire() should return the updated Card object."""
    spike = Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE)
    result = await circuit.fire(spike)

    assert isinstance(result, Card)
    # Should match the cached card
    cached = circuit.get_card(neuron_in_circuit.id)
    assert cached is not None
    assert cached.stability == result.stability


# -- Grade affects FSRS differently -----------------------------------------


@pytest.mark.asyncio
async def test_miss_grade_produces_lower_stability(
    circuit: Circuit,
):
    """Grade.MISS (Again) should produce lower stability than Grade.FIRE (Good)."""
    n_good = Neuron.create("# good item")
    n_miss = Neuron.create("# miss item")
    await circuit.add_neuron(n_good)
    await circuit.add_neuron(n_miss)

    now = datetime.now(timezone.utc)
    card_good = await circuit.fire(
        Spike(neuron_id=n_good.id, grade=Grade.FIRE, fired_at=now)
    )
    card_miss = await circuit.fire(
        Spike(neuron_id=n_miss.id, grade=Grade.MISS, fired_at=now)
    )

    assert card_good.stability > card_miss.stability


@pytest.mark.asyncio
async def test_strong_grade_produces_higher_stability(
    circuit: Circuit,
):
    """Grade.STRONG (Easy) should produce higher stability than Grade.FIRE (Good)."""
    n_good = Neuron.create("# good")
    n_strong = Neuron.create("# strong")
    await circuit.add_neuron(n_good)
    await circuit.add_neuron(n_strong)

    now = datetime.now(timezone.utc)
    card_good = await circuit.fire(
        Spike(neuron_id=n_good.id, grade=Grade.FIRE, fired_at=now)
    )
    card_strong = await circuit.fire(
        Spike(neuron_id=n_strong.id, grade=Grade.STRONG, fired_at=now)
    )

    assert card_strong.stability >= card_good.stability


# -- Multiple reviews -------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_fires_progress_through_states(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """Successive good reviews should progress Learning → Review and increase stability."""
    from fsrs import State

    now = datetime.now(timezone.utc)

    card1 = await circuit.fire(
        Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE, fired_at=now)
    )

    # Second review after due — should transition to Review state
    future = card1.due + timedelta(hours=1)
    card2 = await circuit.fire(
        Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE, fired_at=future)
    )
    assert card2.state == State.Review

    # Third review after due — stability should increase in Review state
    future2 = card2.due + timedelta(hours=1)
    card3 = await circuit.fire(
        Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE, fired_at=future2)
    )
    assert card3.stability > card2.stability


# -- Due neurons query -------------------------------------------------------


@pytest.mark.asyncio
async def test_due_neurons_excludes_recently_reviewed(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """A neuron reviewed just now should NOT be due immediately after."""
    now = datetime.now(timezone.utc)
    await circuit.fire(
        Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE, fired_at=now)
    )

    # Check due right after review — should not be due
    due = await circuit.due_neurons(now=now)
    assert neuron_in_circuit.id not in due


@pytest.mark.asyncio
async def test_due_neurons_includes_past_due(
    circuit: Circuit, neuron_in_circuit: Neuron
):
    """A neuron past its due date should appear in due_neurons()."""
    now = datetime.now(timezone.utc)
    card = await circuit.fire(
        Spike(neuron_id=neuron_in_circuit.id, grade=Grade.FIRE, fired_at=now)
    )

    # Fast forward past due date
    far_future = card.due + timedelta(days=1)
    due = await circuit.due_neurons(now=far_future)
    assert neuron_in_circuit.id in due


# -- FSRS persistence -------------------------------------------------------


@pytest.mark.asyncio
async def test_fsrs_state_persists_across_sessions(tmp_path):
    """FSRS state should survive close/reopen."""
    db_path = tmp_path / "persist.db"

    # Session 1: add neuron + fire
    c1 = Circuit(db_path=db_path)
    await c1.connect()
    n = Neuron.create("# persistent")
    await c1.add_neuron(n)
    now = datetime.now(timezone.utc)
    card1 = await c1.fire(
        Spike(neuron_id=n.id, grade=Grade.FIRE, fired_at=now)
    )
    await c1.close()

    # Session 2: reload
    c2 = Circuit(db_path=db_path)
    await c2.connect()
    card2 = c2.get_card(n.id)
    assert card2 is not None
    assert card2.stability == card1.stability
    assert card2.difficulty == card1.difficulty
    await c2.close()
