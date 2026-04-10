"""Tests for Learn protocol and Flashcard implementation."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fsrs import Card, Rating, Scheduler, State

from spikuit_core import Circuit, Grade, Neuron, SynapseType
from spikuit_core.models import Scaffold, ScaffoldLevel
from spikuit_core.learn import Flashcard, _extract_body, _extract_title


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


SAMPLE = """\
---
type: concept
domain: math
---

# Functor

A mapping between categories that preserves structure.

## Examples

- List is a functor from Hask to Hask.
"""


def _make_neuron(nid: str, content: str = "") -> Neuron:
    return Neuron.create(content or f"# {nid}", id=nid)


# -- Helper tests -----------------------------------------------------------


def test_extract_title():
    assert _extract_title("# Hello World\n\nBody") == "Hello World"
    assert _extract_title("No heading") == ""
    assert _extract_title("---\ntype: x\n---\n\n# Title\n\nBody") == "Title"


def test_extract_body():
    assert _extract_body("# Title\n\nBody text") == "Body text"
    assert _extract_body("---\ntype: x\n---\n\n# Title\n\nBody") == "Body"
    assert _extract_body("---\ntype: x\n---\n\n# Title") == ""


# -- Flashcard.select -------------------------------------------------------


@pytest.mark.asyncio
async def test_flashcard_select_returns_due(circuit):
    """select() returns due neuron IDs."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    # New cards are immediately due
    due = await fc.select()
    assert "n1" in due


@pytest.mark.asyncio
async def test_flashcard_select_respects_limit(circuit):
    """select() respects the limit parameter."""
    for i in range(5):
        await circuit.add_neuron(_make_neuron(f"n{i}"))

    fc = Flashcard(circuit)
    due = await fc.select(limit=2)
    assert len(due) <= 2


# -- Flashcard.present -------------------------------------------------------


@pytest.mark.asyncio
async def test_present_full_shows_everything(circuit):
    """FULL scaffold shows all content."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    scaffold = Scaffold(level=ScaffoldLevel.FULL)
    item = await fc.present("n1", scaffold)
    assert "Functor" in item.question
    assert "mapping between categories" in item.question


@pytest.mark.asyncio
async def test_present_minimal_shows_title_only(circuit):
    """MINIMAL scaffold shows only the title."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    scaffold = Scaffold(level=ScaffoldLevel.MINIMAL)
    item = await fc.present("n1", scaffold)
    assert "Functor" in item.question
    assert "mapping between categories" not in item.question
    # Body should be in the answer
    assert "mapping between categories" in item.answer


@pytest.mark.asyncio
async def test_present_none_shows_title_as_recall(circuit):
    """NONE scaffold shows just the title for pure recall."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    scaffold = Scaffold(level=ScaffoldLevel.NONE)
    item = await fc.present("n1", scaffold)
    assert item.question == "Functor"
    assert SAMPLE in item.answer  # full content in answer


@pytest.mark.asyncio
async def test_present_guided_shows_first_paragraph(circuit):
    """GUIDED scaffold shows title + first paragraph."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    scaffold = Scaffold(level=ScaffoldLevel.GUIDED)
    item = await fc.present("n1", scaffold)
    assert "Functor" in item.question
    assert "mapping between categories" in item.question
    # Should NOT show the examples section in question
    assert "List is a functor" not in item.question


@pytest.mark.asyncio
async def test_present_nonexistent_neuron(circuit):
    """Presenting a missing neuron gives a fallback item."""
    fc = Flashcard(circuit)
    scaffold = Scaffold(level=ScaffoldLevel.FULL)
    item = await fc.present("ghost", scaffold)
    assert "not found" in item.question


@pytest.mark.asyncio
async def test_present_includes_scaffold_hints(circuit):
    """Scaffold context and gaps appear in hints."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    scaffold = Scaffold(
        level=ScaffoldLevel.GUIDED,
        context=["category-theory"],
        gaps=["set-theory"],
    )
    item = await fc.present("n1", scaffold)
    assert any("category-theory" in h for h in item.hints)
    assert any("set-theory" in h for h in item.hints)


# -- Flashcard.evaluate -----------------------------------------------------


def test_evaluate_string_grades():
    """evaluate() parses string grade names."""
    fc = Flashcard.__new__(Flashcard)
    assert fc.evaluate("n1", None, "miss") == Grade.MISS
    assert fc.evaluate("n1", None, "weak") == Grade.WEAK
    assert fc.evaluate("n1", None, "fire") == Grade.FIRE
    assert fc.evaluate("n1", None, "strong") == Grade.STRONG


def test_evaluate_numeric_grades():
    """evaluate() parses numeric grade values."""
    fc = Flashcard.__new__(Flashcard)
    assert fc.evaluate("n1", None, "1") == Grade.MISS
    assert fc.evaluate("n1", None, "2") == Grade.WEAK
    assert fc.evaluate("n1", None, "3") == Grade.FIRE
    assert fc.evaluate("n1", None, "4") == Grade.STRONG


def test_evaluate_default_grade():
    """Unknown input defaults to FIRE."""
    fc = Flashcard.__new__(Flashcard)
    assert fc.evaluate("n1", None, "whatever") == Grade.FIRE


# -- Flashcard.record -------------------------------------------------------


@pytest.mark.asyncio
async def test_record_fires_spike(circuit):
    """record() fires a spike through the circuit."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    card_before = circuit.get_card("n1")
    assert card_before is not None

    await fc.record("n1", Grade.FIRE)

    card_after = circuit.get_card("n1")
    # Card should have advanced (due date changed)
    assert card_after.due != card_before.due


# -- scaffold() helper on Learn base ----------------------------------------


@pytest.mark.asyncio
async def test_learn_scaffold_helper(circuit):
    """Learn.scaffold() delegates to compute_scaffold."""
    n = _make_neuron("n1", SAMPLE)
    await circuit.add_neuron(n)

    fc = Flashcard(circuit)
    scaffold = fc.scaffold("n1")
    assert scaffold.level == ScaffoldLevel.FULL  # new card
