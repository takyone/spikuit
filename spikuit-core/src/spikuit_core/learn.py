"""Learn — abstract protocol for knowledge acquisition sessions.

Learn is the abstraction layer between Brain (Circuit) and external
interactions (Quiz, Flashcard, Import, Conversation). Each Learn
implementation defines how to select, present, evaluate, and record.

Scaffolding is a cross-cutting concern: every Learn type uses it to
adapt difficulty and support level.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .models import Grade, QuizItem, QuizResult, Scaffold, Spike
from .scaffold import compute_scaffold

if TYPE_CHECKING:
    from .circuit import Circuit


class Learn(ABC):
    """Abstract base for learning session strategies.

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
    def evaluate(self, neuron_id: str, item: QuizItem, response: str) -> Grade:
        """Evaluate a learner's response and return a grade."""
        ...


class Flashcard(Learn):
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
            )

        content = neuron.content
        title = _extract_title(content)
        body = _extract_body(content)

        from .models import ScaffoldLevel

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
        )

    def evaluate(self, neuron_id: str, item: QuizItem, response: str) -> Grade:
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


# -- Helpers -----------------------------------------------------------------


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
