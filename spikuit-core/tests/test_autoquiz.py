"""Tests for AutoQuiz and quiz item persistence."""

import pytest
import pytest_asyncio

from spikuit_core import (
    AutoQuiz,
    Circuit,
    Grade,
    Neuron,
    QuizItem,
    QuizItemRole,
    ScaffoldLevel,
)
from spikuit_core.models import QuizRequest, Scaffold


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    n1 = Neuron.create("# Functor\n\nA mapping between categories.", id="n1", type="concept", domain="math")
    n2 = Neuron.create("# Monad\n\nA monoid in endofunctors.", id="n2", type="concept", domain="math")
    await c.add_neuron(n1)
    await c.add_neuron(n2)
    await c.add_synapse("n2", "n1", type=__import__("spikuit_core").SynapseType.REQUIRES)
    yield c
    await c.close()


# -- QuizItem persistence ---------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get_quiz_item(circuit):
    """Quiz items can be stored and retrieved by neuron ID."""
    item = QuizItem(
        question="What is a Functor?",
        answer="A mapping between categories.",
        hints=["Think about morphisms."],
        grading_criteria="Must mention categories.",
        scaffold_level=ScaffoldLevel.MINIMAL,
        neuron_ids={"n1": QuizItemRole.PRIMARY},
    )
    await circuit.add_quiz_item(item)

    items = await circuit.get_quiz_items("n1")
    assert len(items) == 1
    assert items[0].id == item.id
    assert items[0].question == "What is a Functor?"
    assert items[0].hints == ["Think about morphisms."]
    assert items[0].neuron_ids == {"n1": QuizItemRole.PRIMARY}


@pytest.mark.asyncio
async def test_quiz_item_mn_association(circuit):
    """A quiz item can reference multiple neurons."""
    item = QuizItem(
        question="How does Monad relate to Functor?",
        answer="Monad extends Functor.",
        neuron_ids={
            "n2": QuizItemRole.PRIMARY,
            "n1": QuizItemRole.SUPPORTING,
        },
    )
    await circuit.add_quiz_item(item)

    # Find via primary
    items = await circuit.get_quiz_items("n2", role=QuizItemRole.PRIMARY)
    assert len(items) == 1
    assert items[0].primary_neuron_ids == ["n2"]
    assert items[0].supporting_neuron_ids == ["n1"]

    # Find via supporting
    items = await circuit.get_quiz_items("n1", role=QuizItemRole.SUPPORTING)
    assert len(items) == 1


@pytest.mark.asyncio
async def test_quiz_item_filter_by_scaffold_level(circuit):
    """Quiz items can be filtered by scaffold level."""
    item1 = QuizItem(
        question="Q1", answer="A1",
        scaffold_level=ScaffoldLevel.FULL,
        neuron_ids={"n1": QuizItemRole.PRIMARY},
    )
    item2 = QuizItem(
        question="Q2", answer="A2",
        scaffold_level=ScaffoldLevel.NONE,
        neuron_ids={"n1": QuizItemRole.PRIMARY},
    )
    await circuit.add_quiz_item(item1)
    await circuit.add_quiz_item(item2)

    full = await circuit.get_quiz_items("n1", scaffold_level=ScaffoldLevel.FULL)
    assert len(full) == 1
    assert full[0].question == "Q1"

    none = await circuit.get_quiz_items("n1", scaffold_level=ScaffoldLevel.NONE)
    assert len(none) == 1
    assert none[0].question == "Q2"


@pytest.mark.asyncio
async def test_remove_quiz_item(circuit):
    """Removing a quiz item deletes it and its associations."""
    item = QuizItem(
        question="Q", answer="A",
        neuron_ids={"n1": QuizItemRole.PRIMARY},
    )
    await circuit.add_quiz_item(item)
    assert len(await circuit.get_quiz_items("n1")) == 1

    await circuit.remove_quiz_item(item.id)
    assert len(await circuit.get_quiz_items("n1")) == 0


@pytest.mark.asyncio
async def test_neuron_deletion_cascades_quiz_items(circuit):
    """Deleting a neuron removes its primary quiz items."""
    item = QuizItem(
        question="Q", answer="A",
        neuron_ids={"n1": QuizItemRole.PRIMARY},
    )
    await circuit.add_quiz_item(item)

    await circuit.remove_neuron("n1")
    # Item should be gone
    got = await circuit._db.get_quiz_item(item.id)
    assert got is None


@pytest.mark.asyncio
async def test_add_quiz_item_requires_primary(circuit):
    """Adding a quiz item without a PRIMARY neuron raises ValueError."""
    item = QuizItem(
        question="Q", answer="A",
        neuron_ids={"n1": QuizItemRole.SUPPORTING},
    )
    with pytest.raises(ValueError, match="PRIMARY"):
        await circuit.add_quiz_item(item)


# -- AutoQuiz with stored items (preview mode) ------------------------------


@pytest.mark.asyncio
async def test_autoquiz_preview_from_stored(circuit):
    """AutoQuiz presents stored items without needing generate_fn."""
    item = QuizItem(
        question="What is a Functor?",
        answer="A mapping between categories.",
        scaffold_level=ScaffoldLevel.FULL,
        neuron_ids={"n1": QuizItemRole.PRIMARY},
    )
    await circuit.add_quiz_item(item)

    quiz = AutoQuiz(circuit)  # no generate_fn
    scaffold = Scaffold(level=ScaffoldLevel.FULL)
    presented = await quiz.present("n1", scaffold)
    assert presented.question == "What is a Functor?"


@pytest.mark.asyncio
async def test_autoquiz_fallback_to_flashcard(circuit):
    """AutoQuiz falls back to flashcard when no stored items and no generate_fn."""
    quiz = AutoQuiz(circuit)
    scaffold = Scaffold(level=ScaffoldLevel.MINIMAL)
    presented = await quiz.present("n1", scaffold)
    assert "Functor" in presented.question
    assert presented.neuron_ids["n1"] == QuizItemRole.PRIMARY


# -- AutoQuiz with generate_fn (generate mode) ------------------------------


@pytest.mark.asyncio
async def test_autoquiz_generate_and_store(circuit):
    """AutoQuiz generates via callback and stores the result."""
    async def mock_generate(req: QuizRequest) -> QuizItem:
        return QuizItem(
            question=f"Explain {req.primary}",
            answer="The answer",
            hints=["Hint 1"],
        )

    quiz = AutoQuiz(circuit, generate_fn=mock_generate, store=True)
    scaffold = Scaffold(level=ScaffoldLevel.GUIDED)
    presented = await quiz.present("n1", scaffold)

    assert presented.question == "Explain n1"
    assert presented.neuron_ids["n1"] == QuizItemRole.PRIMARY
    assert presented.scaffold_level == ScaffoldLevel.GUIDED

    # Should be persisted
    stored = await circuit.get_quiz_items("n1")
    assert len(stored) == 1
    assert stored[0].id == presented.id


@pytest.mark.asyncio
async def test_autoquiz_generate_no_store(circuit):
    """AutoQuiz generates but does not store when store=False."""
    async def mock_generate(req: QuizRequest) -> QuizItem:
        return QuizItem(question="Q", answer="A")

    quiz = AutoQuiz(circuit, generate_fn=mock_generate, store=False)
    scaffold = Scaffold(level=ScaffoldLevel.FULL)
    await quiz.present("n1", scaffold)

    stored = await circuit.get_quiz_items("n1")
    assert len(stored) == 0


# -- AutoQuiz evaluate ------------------------------------------------------


@pytest.mark.asyncio
async def test_autoquiz_evaluate_with_grade_fn(circuit):
    """AutoQuiz uses grade_fn callback when provided."""
    async def mock_grade(item: QuizItem, response: str) -> Grade:
        return Grade.STRONG if "correct" in response else Grade.MISS

    quiz = AutoQuiz(circuit, grade_fn=mock_grade)
    item = QuizItem(question="Q", answer="A")

    assert await quiz.evaluate("n1", item, "correct answer") == Grade.STRONG
    assert await quiz.evaluate("n1", item, "wrong") == Grade.MISS


@pytest.mark.asyncio
async def test_autoquiz_evaluate_selfgrade_fallback(circuit):
    """AutoQuiz falls back to self-grading without grade_fn."""
    quiz = AutoQuiz(circuit)
    item = QuizItem(question="Q", answer="A")

    assert await quiz.evaluate("n1", item, "fire") == Grade.FIRE
    assert await quiz.evaluate("n1", item, "miss") == Grade.MISS
