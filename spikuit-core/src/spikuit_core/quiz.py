"""Quiz — abstract protocol for review/quiz strategies.

Quiz is the abstraction layer between Brain (Circuit) and review
interactions (Flashcard, AutoQuiz, ...). Each Quiz implementation
defines how to select, present, evaluate, and record.

Scaffolding is a cross-cutting concern: every Quiz type uses it to
adapt difficulty and support level.

Implementations:
    Flashcard: Self-grade, no LLM required.
    AutoQuiz: LLM-generated questions with programmatic or LLM grading.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from .models import Grade, QuizItem, QuizItemRole, QuizRequest, Scaffold, ScaffoldLevel, Spike
from .scaffold import compute_scaffold

if TYPE_CHECKING:
    from .circuit import Circuit


class Quiz(ABC):
    """Abstract base for quiz/review strategies.

    Subclasses implement the select → scaffold → present → evaluate → record
    loop. The base class provides common helpers for scaffolding and recording.
    """

    def __init__(self, circuit: Circuit) -> None:
        self.circuit = circuit

    def scaffold(self, neuron_id: str) -> Scaffold:
        """Compute scaffolding for a neuron."""
        return compute_scaffold(self.circuit, neuron_id)

    async def record(self, neuron_id: str, grade: Grade) -> None:
        """Record a review result via Circuit.fire()."""
        spike = Spike(neuron_id=neuron_id, grade=grade)
        await self.circuit.fire(spike)

    @abstractmethod
    async def select(self, *, limit: int = 10) -> list[str]:
        """Select neuron IDs for this session."""
        ...

    @abstractmethod
    async def present(self, neuron_id: str, scaffold: Scaffold) -> QuizItem:
        """Generate a presentation (question/prompt) for the neuron."""
        ...

    @abstractmethod
    async def evaluate(self, neuron_id: str, item: QuizItem, response: str) -> Grade:
        """Evaluate a learner's response and return a grade."""
        ...


class Flashcard(Quiz):
    """Simple flashcard-style learning — show content, self-grade.

    No LLM required. The learner sees the neuron content and grades
    themselves. Scaffold level affects how much content is revealed
    (FULL = show everything, NONE = show only title).
    """

    async def select(self, *, limit: int = 10) -> list[str]:
        """Select due neurons for flashcard review."""
        return await self.circuit.due_neurons(limit=limit)

    async def present(self, neuron_id: str, scaffold: Scaffold) -> QuizItem:
        """Present neuron as a flashcard.

        Scaffold level controls how much is shown:
        - FULL: show full content as the "question" (study mode)
        - GUIDED: show title + first paragraph, hide rest
        - MINIMAL: show only the title
        - NONE: show only the neuron ID (pure recall)
        """
        neuron = await self.circuit.get_neuron(neuron_id)
        if neuron is None:
            return QuizItem(
                question=f"[Neuron {neuron_id} not found]",
                answer="",
                neuron_ids={neuron_id: QuizItemRole.PRIMARY},
            )

        content = neuron.content
        title = _extract_title(content)
        body = _extract_body(content)

        if scaffold.level == ScaffoldLevel.FULL:
            question = content
            answer = ""
        elif scaffold.level == ScaffoldLevel.GUIDED:
            first_para = body.split("\n\n")[0] if body else ""
            question = f"# {title}\n\n{first_para}" if title else first_para
            answer = body
        elif scaffold.level == ScaffoldLevel.MINIMAL:
            question = f"# {title}" if title else neuron_id
            answer = body
        else:  # NONE
            question = title or neuron_id
            answer = content

        hints = []
        if scaffold.context:
            hints.append(f"Related concepts you know well: {', '.join(scaffold.context)}")
        if scaffold.gaps:
            hints.append(f"Prerequisites to review: {', '.join(scaffold.gaps)}")

        return QuizItem(
            question=question,
            answer=answer,
            hints=hints,
            neuron_ids={neuron_id: QuizItemRole.PRIMARY},
            scaffold_level=scaffold.level,
        )

    async def evaluate(self, neuron_id: str, item: QuizItem, response: str) -> Grade:
        """Self-grading: the response IS the grade.

        Accepts: 'miss', 'weak', 'fire', 'strong' (or their int values 1-4).
        """
        response = response.strip().lower()
        grade_map = {
            "miss": Grade.MISS, "1": Grade.MISS,
            "weak": Grade.WEAK, "2": Grade.WEAK,
            "fire": Grade.FIRE, "3": Grade.FIRE,
            "strong": Grade.STRONG, "4": Grade.STRONG,
        }
        return grade_map.get(response, Grade.FIRE)


# -- Type aliases for AutoQuiz callbacks ------------------------------------

GenerateFn = Callable[[QuizRequest], Awaitable[QuizItem]]
GradeFn = Callable[[QuizItem, str], Awaitable[Grade]]


class AutoQuiz(Quiz):
    """LLM-powered quiz — generate questions and grade answers.

    Uses callback functions for LLM operations so the core engine
    stays LLM-independent. If no callbacks are provided, falls back
    to stored quiz items (preview mode) or Flashcard-style presentation.

    Args:
        circuit: The knowledge graph engine.
        generate_fn: Async callback ``(QuizRequest) -> QuizItem`` for
            generating new quiz questions via LLM.
        grade_fn: Async callback ``(QuizItem, response) -> Grade`` for
            grading answers via LLM. If ``None``, falls back to self-grading.
        store: Whether to persist generated QuizItems to the database.
    """

    def __init__(
        self,
        circuit: Circuit,
        *,
        generate_fn: GenerateFn | None = None,
        grade_fn: GradeFn | None = None,
        store: bool = True,
    ) -> None:
        super().__init__(circuit)
        self.generate_fn = generate_fn
        self.grade_fn = grade_fn
        self.store = store

    async def select(self, *, limit: int = 10) -> list[str]:
        """Select due neurons for quiz."""
        return await self.circuit.due_neurons(limit=limit)

    async def present(self, neuron_id: str, scaffold: Scaffold) -> QuizItem:
        """Present a quiz item for a neuron.

        Resolution order:
        1. Stored quiz items matching this neuron + scaffold level (preview)
        2. Stored quiz items matching this neuron at any level (preview)
        3. LLM generation via ``generate_fn`` (generate)
        4. Flashcard-style fallback (no LLM)
        """
        # 1. Try stored items at matching scaffold level
        items = await self.circuit.get_quiz_items(
            neuron_id, role=QuizItemRole.PRIMARY, scaffold_level=scaffold.level,
        )
        if items:
            return random.choice(items)

        # 2. Try stored items at any level
        items = await self.circuit.get_quiz_items(
            neuron_id, role=QuizItemRole.PRIMARY,
        )
        if items:
            return random.choice(items)

        # 3. Generate via LLM
        if self.generate_fn is not None:
            req = QuizRequest(
                primary=neuron_id,
                supporting=scaffold.context,
                scaffold=scaffold,
            )
            item = await self.generate_fn(req)
            # Ensure neuron association is set
            if neuron_id not in item.neuron_ids:
                item.neuron_ids[neuron_id] = QuizItemRole.PRIMARY
            for sid in scaffold.context:
                if sid not in item.neuron_ids:
                    item.neuron_ids[sid] = QuizItemRole.SUPPORTING
            if item.scaffold_level is None:
                item.scaffold_level = scaffold.level
            if self.store:
                await self.circuit.add_quiz_item(item)
            return item

        # 4. Flashcard fallback
        return await _flashcard_fallback(self.circuit, neuron_id, scaffold)

    async def evaluate(self, neuron_id: str, item: QuizItem, response: str) -> Grade:
        """Grade a response — via LLM callback or self-grade fallback."""
        if self.grade_fn is not None:
            return await self.grade_fn(item, response)
        # Self-grade fallback
        response = response.strip().lower()
        grade_map = {
            "miss": Grade.MISS, "1": Grade.MISS,
            "weak": Grade.WEAK, "2": Grade.WEAK,
            "fire": Grade.FIRE, "3": Grade.FIRE,
            "strong": Grade.STRONG, "4": Grade.STRONG,
        }
        return grade_map.get(response, Grade.FIRE)


# -- Helpers ----------------------------------------------------------------


async def _flashcard_fallback(
    circuit: Circuit, neuron_id: str, scaffold: Scaffold,
) -> QuizItem:
    """Generate a Flashcard-style QuizItem as fallback."""
    neuron = await circuit.get_neuron(neuron_id)
    if neuron is None:
        return QuizItem(
            question=f"[Neuron {neuron_id} not found]",
            answer="",
            neuron_ids={neuron_id: QuizItemRole.PRIMARY},
        )

    content = neuron.content
    title = _extract_title(content)
    body = _extract_body(content)

    if scaffold.level == ScaffoldLevel.FULL:
        question, answer = content, ""
    elif scaffold.level == ScaffoldLevel.GUIDED:
        first_para = body.split("\n\n")[0] if body else ""
        question = f"# {title}\n\n{first_para}" if title else first_para
        answer = body
    elif scaffold.level == ScaffoldLevel.MINIMAL:
        question = f"# {title}" if title else neuron_id
        answer = body
    else:
        question = title or neuron_id
        answer = content

    return QuizItem(
        question=question,
        answer=answer,
        neuron_ids={neuron_id: QuizItemRole.PRIMARY},
        scaffold_level=scaffold.level,
    )


def _extract_title(content: str) -> str:
    """Extract the first Markdown heading from content."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _extract_body(content: str) -> str:
    """Extract body text after frontmatter and first heading."""
    text = content
    # Strip frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    # Strip first heading
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()
