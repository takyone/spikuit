"""Tests for Scaffold — ZPD-inspired scaffolding from FSRS state + graph."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fsrs import Card, Rating, Scheduler, State

from spikuit_core import Circuit, Grade, Neuron, Spike, SynapseType
from spikuit_core.models import Scaffold, ScaffoldLevel
from spikuit_core.scaffold import compute_scaffold


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


def _make_neuron(nid: str, content: str = "") -> Neuron:
    return Neuron.create(content or f"# {nid}", id=nid)


def _advance_card_to_review(card: Card, scheduler: Scheduler, stability: float) -> Card:
    """Advance a card to Review state with approximate target stability.

    Fire enough Good reviews to reach Review state, then set stability directly.
    """
    now = datetime.now(timezone.utc)
    # Move from New → Learning → Review with repeated Good ratings
    for _ in range(5):
        card, _ = scheduler.review_card(card, Rating.Good, now)
    # Override stability for test control
    card.stability = stability
    card.state = State.Review
    return card


# -- Level from FSRS state --------------------------------------------------


@pytest.mark.asyncio
async def test_new_neuron_gets_full_scaffold(circuit):
    """New neurons (no card) → FULL scaffold."""
    n = _make_neuron("n1")
    await circuit.add_neuron(n)
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.level == ScaffoldLevel.FULL


@pytest.mark.asyncio
async def test_unknown_neuron_gets_full_scaffold(circuit):
    """Neuron not in circuit → FULL scaffold."""
    scaffold = compute_scaffold(circuit, "nonexistent")
    assert scaffold.level == ScaffoldLevel.FULL


@pytest.mark.asyncio
async def test_learning_state_gives_full(circuit):
    """Learning state → FULL scaffold."""
    n = _make_neuron("n1")
    await circuit.add_neuron(n)
    # Card starts as New (which maps to FULL)
    card = circuit.get_card("n1")
    assert card is not None
    assert card.state == State.Learning
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.level == ScaffoldLevel.FULL


@pytest.mark.asyncio
async def test_review_low_stability_gives_guided(circuit):
    """Review state with low stability (<5) → GUIDED."""
    n = _make_neuron("n1")
    await circuit.add_neuron(n)
    card = circuit.get_card("n1")
    card = _advance_card_to_review(card, circuit._scheduler, stability=3.0)
    circuit._cards["n1"] = card
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.level == ScaffoldLevel.GUIDED


@pytest.mark.asyncio
async def test_review_mid_stability_gives_minimal(circuit):
    """Review state with mid stability (5-21) → MINIMAL."""
    n = _make_neuron("n1")
    await circuit.add_neuron(n)
    card = circuit.get_card("n1")
    card = _advance_card_to_review(card, circuit._scheduler, stability=10.0)
    circuit._cards["n1"] = card
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.level == ScaffoldLevel.MINIMAL


@pytest.mark.asyncio
async def test_review_high_stability_gives_none(circuit):
    """Review state with high stability (>=21) → NONE."""
    n = _make_neuron("n1")
    await circuit.add_neuron(n)
    card = circuit.get_card("n1")
    card = _advance_card_to_review(card, circuit._scheduler, stability=30.0)
    circuit._cards["n1"] = card
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.level == ScaffoldLevel.NONE


@pytest.mark.asyncio
async def test_relearning_gives_guided(circuit):
    """Relearning state → GUIDED."""
    n = _make_neuron("n1")
    await circuit.add_neuron(n)
    card = circuit.get_card("n1")
    card = _advance_card_to_review(card, circuit._scheduler, stability=10.0)
    card.state = State.Relearning
    circuit._cards["n1"] = card
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.level == ScaffoldLevel.GUIDED


# -- Context and gaps from graph neighbors -----------------------------------


@pytest.mark.asyncio
async def test_strong_neighbor_becomes_context(circuit):
    """A well-known neighbor (Review, stability>5) is scaffolding context."""
    n1 = _make_neuron("n1")
    n2 = _make_neuron("n2")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse("n1", "n2", SynapseType.REQUIRES)

    # Make n2 strong
    card2 = circuit.get_card("n2")
    card2 = _advance_card_to_review(card2, circuit._scheduler, stability=10.0)
    circuit._cards["n2"] = card2

    scaffold = compute_scaffold(circuit, "n1")
    assert "n2" in scaffold.context


@pytest.mark.asyncio
async def test_weak_prerequisite_becomes_gap(circuit):
    """A weak prerequisite (requires edge, low stability) is a gap."""
    n1 = _make_neuron("n1")
    n2 = _make_neuron("n2")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse("n1", "n2", SynapseType.REQUIRES)

    # n2 stays as New card (weak) — should be a gap
    scaffold = compute_scaffold(circuit, "n1")
    assert "n2" in scaffold.gaps


@pytest.mark.asyncio
async def test_no_card_neighbor_is_gap(circuit):
    """A neighbor with no FSRS card is treated as a gap."""
    n1 = _make_neuron("n1")
    n2 = _make_neuron("n2")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse("n1", "n2", SynapseType.REQUIRES)

    # Remove n2's card from cache
    del circuit._cards["n2"]

    scaffold = compute_scaffold(circuit, "n1")
    assert "n2" in scaffold.gaps


@pytest.mark.asyncio
async def test_predecessor_can_be_context(circuit):
    """Incoming edges: a strong predecessor adds to context."""
    n1 = _make_neuron("n1")
    n2 = _make_neuron("n2")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    # n2 requires n1 → n2 is predecessor of n1 conceptually,
    # but in graph terms: edge n2→n1, so n2 is predecessor of n1
    await circuit.add_synapse("n2", "n1", SynapseType.REQUIRES)

    # Make n2 strong
    card2 = circuit.get_card("n2")
    card2 = _advance_card_to_review(card2, circuit._scheduler, stability=10.0)
    circuit._cards["n2"] = card2

    scaffold = compute_scaffold(circuit, "n1")
    assert "n2" in scaffold.context


@pytest.mark.asyncio
async def test_extends_neighbor_not_gap(circuit):
    """Non-requires edge types don't create gaps (only requires does)."""
    n1 = _make_neuron("n1")
    n2 = _make_neuron("n2")
    await circuit.add_neuron(n1)
    await circuit.add_neuron(n2)
    await circuit.add_synapse("n1", "n2", SynapseType.EXTENDS)

    # n2 is weak (New state) but connected via 'extends', not 'requires'
    scaffold = compute_scaffold(circuit, "n1")
    assert "n2" not in scaffold.gaps


@pytest.mark.asyncio
async def test_isolated_neuron_no_context_no_gaps(circuit):
    """A neuron with no edges has empty context and gaps."""
    n1 = _make_neuron("n1")
    await circuit.add_neuron(n1)
    scaffold = compute_scaffold(circuit, "n1")
    assert scaffold.context == []
    assert scaffold.gaps == []
