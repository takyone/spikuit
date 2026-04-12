"""TutorSession — 1-on-1 scaffolded tutoring session.

Uses a Quiz strategy (AutoQuiz or Flashcard) internally to generate
questions and evaluate answers, adding hint progression, gap detection,
and retry logic on top.

Flow:
    start(neuron_ids) → teach() → respond(answer) / hint() / skip() → teach() → ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from .models import Grade, QuizItem, Scaffold
from .quiz import Quiz
from .scaffold import compute_scaffold

if TYPE_CHECKING:
    from .circuit import Circuit


class TutorState(msgspec.Struct, kw_only=True):
    """State of the current tutoring interaction.

    Attributes:
        neuron_id: The neuron being tutored.
        item: The quiz item presented to the learner.
        scaffold: Scaffolding state for this neuron.
        hints_used: Number of hints revealed so far.
        attempts: Number of answer attempts made.
        grade: Final grade (``None`` while unanswered).
        revealed: Whether the answer has been revealed.
    """

    neuron_id: str
    item: QuizItem
    scaffold: Scaffold
    hints_used: int = 0
    attempts: int = 0
    grade: Grade | None = None
    revealed: bool = False


class TutorSession:
    """1-on-1 scaffolded tutoring — hint progression, gap detection, retry.

    Args:
        circuit: The knowledge graph engine.
        quiz: Quiz strategy to use (AutoQuiz, Flashcard, etc.).
        persist: Whether to commit results on close.
        max_attempts: Max answer attempts before revealing the answer.

    Example:
        ```python
        tutor = TutorSession(circuit, quiz=AutoQuiz(circuit))
        queue = await tutor.start(limit=5)

        state = await tutor.teach()       # present first question
        state = await tutor.respond("42") # evaluate answer
        if state.grade in (Grade.MISS, Grade.WEAK):
            h = tutor.hint()              # get next hint
            state = await tutor.respond("monad")  # retry
        state = await tutor.teach()       # next neuron
        ```
    """

    def __init__(
        self,
        circuit: Circuit,
        *,
        quiz: Quiz,
        persist: bool = True,
        max_attempts: int = 3,
    ) -> None:
        self.circuit = circuit
        self.quiz = quiz
        self.persist = persist
        self.max_attempts = max_attempts

        self._queue: list[str] = []
        self._current: TutorState | None = None
        self._history: list[TutorState] = []

    # -- Lifecycle ----------------------------------------------------------

    async def start(
        self,
        neuron_ids: list[str] | None = None,
        *,
        limit: int = 10,
    ) -> list[str]:
        """Build the tutoring queue.

        If ``neuron_ids`` is provided, uses those. Otherwise selects
        due neurons via the Quiz strategy. Weak prerequisites (gaps)
        are inserted before their dependents.

        Args:
            neuron_ids: Explicit neuron IDs to tutor.
            limit: Max neurons to select if ``neuron_ids`` is ``None``.

        Returns:
            The ordered queue of neuron IDs.
        """
        if neuron_ids is not None:
            ids = list(neuron_ids)
        else:
            ids = await self.quiz.select(limit=limit)

        # Expand gaps: insert weak prerequisites before their dependents
        expanded: list[str] = []
        seen: set[str] = set()
        for nid in ids:
            scaffold = compute_scaffold(self.circuit, nid)
            for gap in scaffold.gaps:
                if gap not in seen:
                    expanded.append(gap)
                    seen.add(gap)
            if nid not in seen:
                expanded.append(nid)
                seen.add(nid)

        self._queue = expanded
        self._current = None
        return list(self._queue)

    async def teach(self) -> TutorState | None:
        """Present the next neuron in the queue.

        Finalizes the current neuron (if any) and advances to the next.
        Returns ``None`` when the queue is empty.
        """
        # Finalize current if still open
        if self._current is not None and self._current.grade is None:
            await self._finalize(self._current, Grade.MISS)

        if not self._queue:
            return None

        neuron_id = self._queue.pop(0)
        scaffold = compute_scaffold(self.circuit, neuron_id)
        item = await self.quiz.present(neuron_id, scaffold)

        self._current = TutorState(
            neuron_id=neuron_id,
            item=item,
            scaffold=scaffold,
        )
        return self._current

    async def respond(self, answer: str) -> TutorState:
        """Submit an answer for the current question.

        On MISS/WEAK with remaining attempts, the state stays open
        for retry (call ``hint()`` then ``respond()`` again).
        On FIRE/STRONG or max attempts reached, the result is recorded
        and the state is finalized.

        Args:
            answer: The learner's response.

        Returns:
            Updated TutorState with grade set.

        Raises:
            RuntimeError: If no question is active (call ``teach()`` first).
        """
        if self._current is None:
            raise RuntimeError("No active question. Call teach() first.")

        if self._current.grade is not None and self._current.grade >= Grade.FIRE:
            raise RuntimeError("Already answered correctly. Call teach() to advance.")

        state = self._current
        state.attempts += 1

        grade = await self.quiz.evaluate(state.neuron_id, state.item, answer)
        state.grade = grade

        if grade >= Grade.FIRE:
            # Correct — record and finalize
            await self._finalize(state, grade)
        elif state.attempts >= self.max_attempts:
            # Max attempts — reveal answer, record as MISS
            state.revealed = True
            await self._finalize(state, Grade.MISS)
        # else: MISS/WEAK with attempts left — keep state open for hint + retry

        return state

    def hint(self) -> str | None:
        """Reveal the next progressive hint.

        Returns ``None`` when all hints are exhausted.
        """
        if self._current is None:
            return None

        hints = self._current.item.hints
        idx = self._current.hints_used
        if idx < len(hints):
            self._current.hints_used += 1
            return hints[idx]
        return None

    async def skip(self) -> TutorState | None:
        """Skip the current question without grading.

        Returns the skipped state, or ``None`` if nothing was active.
        """
        if self._current is None:
            return None

        state = self._current
        state.revealed = True
        # Don't fire — no FSRS update for skipped items
        self._history.append(state)
        self._current = None
        return state

    async def close(self) -> None:
        """End the session. Finalizes any open question."""
        if self._current is not None and self._current.grade is None:
            await self._finalize(self._current, Grade.MISS)
        self._current = None

    def reset(self) -> None:
        """Reset session state."""
        self._queue.clear()
        self._current = None
        self._history.clear()

    # -- Properties ---------------------------------------------------------

    @property
    def current(self) -> TutorState | None:
        """The currently active tutor state."""
        return self._current

    @property
    def queue(self) -> list[str]:
        """Remaining neuron IDs in the queue."""
        return list(self._queue)

    @property
    def stats(self) -> dict:
        """Session statistics.

        Returns:
            Dict with taught, correct, weak, missed, hinted, skipped, remaining.
        """
        graded = [s for s in self._history if s.grade is not None]
        return {
            "taught": len(self._history),
            "correct": sum(1 for s in graded if s.grade >= Grade.FIRE),
            "weak": sum(1 for s in graded if s.grade == Grade.WEAK),
            "missed": sum(1 for s in graded if s.grade == Grade.MISS),
            "hinted": sum(1 for s in self._history if s.hints_used > 0),
            "skipped": sum(1 for s in self._history if s.grade is None),
            "remaining": len(self._queue),
        }

    # -- Internal -----------------------------------------------------------

    async def _finalize(self, state: TutorState, grade: Grade) -> None:
        """Record the grade and move state to history."""
        state.grade = grade
        await self.quiz.record(state.neuron_id, grade)
        self._history.append(state)
        if self._current is state:
            self._current = None
