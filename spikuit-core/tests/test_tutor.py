"""Tests for TutorSession — scaffolded 1-on-1 tutoring."""

import pytest
import pytest_asyncio

from spikuit_core import (
    Circuit,
    Grade,
    Neuron,
    QuizItem,
    QuizItemRole,
    SynapseType,
    TutorSession,
    TutorState,
)
from spikuit_core.learn import Flashcard
from spikuit_core.models import Scaffold, ScaffoldLevel


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    # n1 requires n2 (n2 is prerequisite)
    n1 = Neuron.create("# Monad\n\nA monoid in endofunctors.", id="n1")
    n2 = Neuron.create("# Functor\n\nA mapping between categories.", id="n2")
    n3 = Neuron.create("# Applicative\n\nBetween Functor and Monad.", id="n3")
    await c.add_neuron(n1)
    await c.add_neuron(n2)
    await c.add_neuron(n3)
    await c.add_synapse("n1", "n2", type=SynapseType.REQUIRES)
    yield c
    await c.close()


def _make_tutor(circuit, **kwargs):
    return TutorSession(circuit, learn=Flashcard(circuit), **kwargs)


# -- start() ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_with_explicit_ids(circuit):
    """start() uses provided neuron IDs."""
    tutor = _make_tutor(circuit)
    queue = await tutor.start(["n1", "n3"])
    # n1 has gap n2 (requires), so n2 should be inserted before n1
    assert "n2" in queue
    assert queue.index("n2") < queue.index("n1")


@pytest.mark.asyncio
async def test_start_deduplicates(circuit):
    """start() does not duplicate IDs when gap overlaps with queue."""
    tutor = _make_tutor(circuit)
    queue = await tutor.start(["n2", "n1"])
    assert queue.count("n2") == 1


# -- teach() ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_teach_returns_state(circuit):
    """teach() returns a TutorState with question."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3"])
    state = await tutor.teach()

    assert state is not None
    assert isinstance(state, TutorState)
    assert state.neuron_id == "n3"
    assert state.item.question != ""
    assert state.attempts == 0
    assert state.grade is None


@pytest.mark.asyncio
async def test_teach_returns_none_when_empty(circuit):
    """teach() returns None when queue is exhausted."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3"])
    await tutor.teach()
    await tutor.respond("fire")
    state = await tutor.teach()
    assert state is None


# -- respond() --------------------------------------------------------------


@pytest.mark.asyncio
async def test_respond_correct(circuit):
    """Correct answer finalizes the question."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3"])
    await tutor.teach()
    state = await tutor.respond("fire")

    assert state.grade == Grade.FIRE
    assert state.attempts == 1
    assert tutor.current is None  # finalized


@pytest.mark.asyncio
async def test_respond_wrong_allows_retry(circuit):
    """Wrong answer keeps the question open for retry."""
    tutor = _make_tutor(circuit, max_attempts=3)
    await tutor.start(["n3"])
    await tutor.teach()
    state = await tutor.respond("miss")

    assert state.grade == Grade.MISS
    assert state.attempts == 1
    # Still open — can retry
    assert tutor.current is not None


@pytest.mark.asyncio
async def test_respond_max_attempts_reveals(circuit):
    """After max attempts, answer is revealed and recorded as MISS."""
    tutor = _make_tutor(circuit, max_attempts=2)
    await tutor.start(["n3"])
    await tutor.teach()

    await tutor.respond("miss")
    state = await tutor.respond("miss")

    assert state.attempts == 2
    assert state.revealed is True
    assert state.grade == Grade.MISS
    assert tutor.current is None  # finalized


@pytest.mark.asyncio
async def test_respond_retry_then_correct(circuit):
    """Wrong answer → hint → correct answer on retry."""
    tutor = _make_tutor(circuit, max_attempts=3)
    await tutor.start(["n3"])
    await tutor.teach()

    state = await tutor.respond("miss")
    assert state.grade == Grade.MISS
    assert tutor.current is not None

    # Retry with correct
    state = await tutor.respond("fire")
    assert state.grade == Grade.FIRE
    assert state.attempts == 2
    assert tutor.current is None


@pytest.mark.asyncio
async def test_respond_raises_without_teach(circuit):
    """respond() raises if no question is active."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3"])
    with pytest.raises(RuntimeError, match="teach"):
        await tutor.respond("fire")


# -- hint() -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_hint_progressive(circuit):
    """hint() reveals hints one at a time."""
    tutor = _make_tutor(circuit)
    # n1 requires n2 — scaffold will have context/gaps
    await tutor.start(["n1"])
    state = await tutor.teach()

    # Keep getting hints until exhausted
    hints = []
    while True:
        h = tutor.hint()
        if h is None:
            break
        hints.append(h)
        assert state.hints_used == len(hints)

    # No more hints
    assert tutor.hint() is None


@pytest.mark.asyncio
async def test_hint_returns_none_without_teach(circuit):
    """hint() returns None when no question is active."""
    tutor = _make_tutor(circuit)
    assert tutor.hint() is None


# -- skip() -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip(circuit):
    """skip() moves past the current question without grading."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3", "n1"])
    await tutor.teach()
    state = await tutor.skip()

    assert state is not None
    assert state.revealed is True
    assert state.grade is None
    assert tutor.current is None


# -- stats ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats(circuit):
    """stats reflects session progress."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3", "n2"])

    await tutor.teach()
    await tutor.respond("fire")

    await tutor.teach()
    await tutor.respond("miss")
    await tutor.respond("miss")
    await tutor.respond("miss")  # max_attempts=3 default

    s = tutor.stats
    assert s["taught"] == 2
    assert s["correct"] == 1
    assert s["missed"] == 1
    assert s["remaining"] == 0


# -- close / reset ----------------------------------------------------------


@pytest.mark.asyncio
async def test_close_finalizes_open(circuit):
    """close() records MISS for any unanswered question."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3"])
    await tutor.teach()
    await tutor.close()

    assert tutor.current is None
    assert tutor.stats["missed"] == 1


@pytest.mark.asyncio
async def test_reset_clears_state(circuit):
    """reset() clears queue and history."""
    tutor = _make_tutor(circuit)
    await tutor.start(["n3"])
    await tutor.teach()
    tutor.reset()

    assert tutor.queue == []
    assert tutor.current is None
    assert tutor.stats["taught"] == 0
