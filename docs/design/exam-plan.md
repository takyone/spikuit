# ExamPlan — Tutor Session Abstraction

**Status**: draft for review
**Target**: v0.6.3 Phase 1
**Prerequisite**: [coaching-theory.md](coaching-theory.md)

## Why ExamPlan

The legacy `TutorSession` walks a flat queue of neuron IDs, presenting
one `Quiz.present()` at a time. This "1 neuron : 1 quiz : immediate
record" loop bakes several assumptions that the coaching survey showed
to be wrong:

- **Retrieval granularity is per-neuron** — but elaborative follow-ups
  span multiple neurons ("how does Functor relate to Category?").
- **Difficulty is fixed per neuron** — but desirable difficulties wants
  quiz type selection by scaffold level.
- **Transitions are implicit** — hint-on-miss, retry, reveal-answer are
  hardcoded in `TutorSession.respond()`. New transitions (elaborative
  follow-up, mastery re-queue) would mean more imperative branches.
- **Mastery and interleaving have no place to live** — they're
  session-level policies, not per-quiz decisions.

`ExamPlan` is the declarative answer: a session is a **planned sequence
of steps + transition rules + policy knobs**. `TutorSession` becomes a
pure interpreter of an `ExamPlan`.

## Mental model

Think of `ExamPlan` as a finite-state machine where:

- **States** are `ExamStep` instances (a neuron + its chosen Quiz + its
  scaffold + follow-ups).
- **Transitions** are functions keyed by event (`on_grade`, `on_skip`,
  `on_exhausted_attempts`) that return the next action: advance,
  re-queue, branch into follow-up, or terminate.
- **Policy** is the ExamPlan's top-level flags
  (`interleave_by`, `require_mastery`, `elaborate_on_correct`,
  `collect_confidence`, `prompt_template`) that determine which
  transitions are active.

The interpreter (`TutorSession`) never makes pedagogical decisions — it
just walks the FSM the plan describes.

## Layering principle

**LLM dependency ≠ Agent dependency.** A quiz can need an LLM to grade
a free-response answer without needing a full Agent orchestration loop.
v0.6.3 enforces this by placing all LLM-dependent *abstractions* in
`spikuit_cli` behind Protocols that any client can satisfy:

- `spikuit_core` — LLM-free, agent-free (Circuit, Scaffold, FSRS)
- `spikuit_cli` — LLM-capable via injected Protocols, agent-free
  (Quiz types, ExamPlan, TutorSession, LLMGrader Protocol,
  one-shot LLM client reference impl for LM Studio / Ollama)
- `spikuit_agents` — Agent-powered sessions (currently only an
  `AgentLLMGrader` that implements the Protocol from cli, plus
  future multi-turn LearnSession / QABotSession)

Dependency flow: `core ← cli ← agents`. cli never imports from agents.

## Type sketch

```python
# spikuit-cli/src/spikuit_cli/tutor/plan.py

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from spikuit_core import Grade, Scaffold
from spikuit_cli.quiz import BaseQuiz, QuizResponse, QuizResult


# -- Step-level ------------------------------------------------------------

@dataclass
class FollowUp:
    """A deepening question triggered after a correct answer.

    Follow-ups are LLM-graded for feedback but NEVER fire FSRS.
    Results are transcribed into spike.notes on the parent step.
    """
    prompt: str
    rubric: str                   # how to grade a response
    related_neuron_ids: list[str] = field(default_factory=list)


@dataclass
class FollowUpResult:
    """Outcome of a follow-up. Deliberately NOT a QuizResult.

    The type distinction guarantees follow-ups never reach circuit.fire.
    """
    follow_up: FollowUp
    student_response: str
    correctness: float            # 0.0-1.0 (LLM rubric-graded)
    feedback: str                 # coach note to show learner
    note_for_next_review: str     # transcribed into spike.notes


@dataclass
class ExamStep:
    neuron_id: str
    quiz: BaseQuiz
    scaffold: Scaffold
    follow_ups: list[FollowUp] = field(default_factory=list)

    # Runtime state (mutated by interpreter)
    attempts: int = 0
    requeue_count: int = 0
    confidence: int | None = None         # learner's pre-flip rating 1-4
    final_result: QuizResult | None = None
    follow_up_results: list[FollowUpResult] = field(default_factory=list)


# -- Plan-level -----------------------------------------------------------

class InterleaveMode(str, Enum):
    NONE = "none"
    DOMAIN = "domain"
    COMMUNITY = "community"


@dataclass
class ExamPlan:
    steps: list[ExamStep]

    # Policy knobs (from coaching survey)
    interleave_by: InterleaveMode = InterleaveMode.NONE
    require_mastery: bool = False
    mastery_max_requeues: int = 2
    elaborate_on_correct: bool = False
    collect_confidence: bool = True
    max_attempts: int = 3
    prompt_template: str = "default"

    # Derived at build time
    interleave_pull_ratio: float = 0.20   # used if interleave_by != NONE
    near_due_days: int = 2


# -- Transition events ----------------------------------------------------

class TransitionEvent(str, Enum):
    STEP_COMPLETED = "step_completed"      # final grade recorded
    RETRY_NEEDED = "retry_needed"          # MISS/WEAK, attempts left
    REVEAL_ANSWER = "reveal_answer"        # max attempts reached
    ENTER_FOLLOW_UP = "enter_follow_up"    # FIRE/STRONG + elaborate_on_correct
    REQUEUE = "requeue"                    # require_mastery + failed + under cap
    ADVANCE = "advance"                    # move to next step


@dataclass
class TransitionResult:
    event: TransitionEvent
    next_step: ExamStep | None = None      # filled in by interpreter, not transition
    payload: dict = field(default_factory=dict)   # e.g. follow_up to show
```

## Building an ExamPlan

```python
# spikuit-agents/src/spikuit_agents/tutor/builder.py

async def plan_exam(
    circuit: Circuit,
    *,
    neuron_ids: list[str] | None = None,
    limit: int = 10,
    interleave_by: InterleaveMode = InterleaveMode.NONE,
    require_mastery: bool = False,
    elaborate_on_correct: bool = False,
    collect_confidence: bool = True,
    quiz_factory: QuizFactory | None = None,
) -> ExamPlan:
    """Build an ExamPlan from Brain state.

    Flow:
    1. Resolve neuron queue (explicit ids or `circuit.due_neurons`)
    2. Expand gaps: insert weak prerequisites before their dependents
    3. Interleave: if enabled, pull near-due from other domains
    4. For each neuron: compute scaffold, choose quiz type by level
    5. Attach follow-ups if elaborate_on_correct
    6. Return ExamPlan
    """
```

### Gap expansion (inherited from legacy TutorSession)

For each target neuron, walk `scaffold.gaps` and insert any weak
prerequisites *before* the target, deduped across the whole queue.
This keeps the legacy behavior where Tutor teaches Monad only after
making sure Functor is warm.

### Interleave pull

If `interleave_by == DOMAIN`:
1. Count `due` neurons per domain.
2. Identify the dominant domain (> 50% of queue).
3. Call `circuit.near_due_neurons(days_ahead=2, limit=N)` where
   `N = ceil(len(queue) * 0.20)`, filtering out the dominant domain.
4. Interleave so no two consecutive steps share the dominant domain.

**New circuit API needed**: `Circuit.near_due_neurons(days_ahead, limit)`
— returns neuron IDs whose next FSRS review is within `days_ahead` days
but not yet due. Implementation: same SQL as `due_neurons` with a
looser date bound. ~10 LOC.

### Quiz type selection (desirable difficulties)

```python
def _choose_quiz(neuron: Neuron, scaffold: Scaffold) -> BaseQuiz:
    match scaffold.level:
        case ScaffoldLevel.FULL:
            # Warm review, show content as cued recall
            return Flashcard(neuron, scaffold)
        case ScaffoldLevel.GUIDED:
            # Title + hints only, learner works harder
            return Flashcard(neuron, scaffold)  # front auto-hides body
        case ScaffoldLevel.MINIMAL | ScaffoldLevel.NONE:
            # Free response — highest desirable difficulty
            return FreeResponseQuiz(neuron, scaffold)
```

Note: `Flashcard.front()` already consults `scaffold.level` to decide
whether to show the body. That logic stays. What changes is that
`MINIMAL`/`NONE` now routes to `FreeResponseQuiz` instead of the same
flashcard with a hidden body.

### Follow-up attachment

If `elaborate_on_correct=True`, each step gets zero, one, or two
`FollowUp`s based on `scaffold.context`:

```python
if elaborate_on_correct and scaffold.context:
    # Pick the strongest neighbor as the "related concept" anchor
    anchor_id = scaffold.context[0]
    anchor = await circuit.get_neuron(anchor_id)
    step.follow_ups.append(FollowUp(
        prompt=f"How does {neuron.title} relate to {anchor.title}?",
        rubric=f"Correct answers should mention the connection between "
               f"{neuron.title} and {anchor.title} concretely.",
        related_neuron_ids=[anchor_id],
    ))
```

## Running an ExamPlan

```python
# spikuit-agents/src/spikuit_agents/tutor/session.py

class TutorSession:
    """Interprets an ExamPlan. Stateless wrt pedagogy — all policy
    decisions live on the plan itself.
    """

    def __init__(self, circuit: Circuit, plan: ExamPlan, *, persist: bool = True):
        self.circuit = circuit
        self.plan = plan
        self.persist = persist
        self._idx = 0
        self._current: ExamStep | None = None
        self._history: list[ExamStep] = []

    async def teach(self) -> ExamStep | None:
        """Advance to the next step. Returns None when plan is exhausted."""
        if self._idx >= len(self.plan.steps):
            return None
        self._current = self.plan.steps[self._idx]
        return self._current

    async def record_response(self, response: QuizResponse) -> TransitionResult:
        """Feed a learner response into the current step. Returns the
        next transition (advance / retry / follow-up / requeue).
        """
        assert self._current is not None
        step = self._current
        step.attempts += 1
        step.confidence = response.confidence
        result = step.quiz.grade(response)

        if result.grade is None and result.needs_tutor_grading:
            # LLM grading happens upstream — TutorSession gets a
            # complete QuizResult back via grade_with_llm() elsewhere.
            raise NotImplementedError("LLM grading path not wired yet")

        step.final_result = result
        transition = self._transition_on_grade(step, result.grade)
        return transition

    def _transition_on_grade(self, step: ExamStep, grade: Grade) -> TransitionResult:
        # Correct path
        if grade >= Grade.FIRE:
            if self.plan.elaborate_on_correct and step.follow_ups:
                return TransitionResult(
                    event=TransitionEvent.ENTER_FOLLOW_UP,
                    payload={"follow_up": step.follow_ups[0]},
                )
            return self._complete_and_advance(step)

        # Incorrect path
        if step.attempts < self.plan.max_attempts:
            return TransitionResult(event=TransitionEvent.RETRY_NEEDED)

        # Max attempts reached
        if (
            self.plan.require_mastery
            and step.requeue_count < self.plan.mastery_max_requeues
        ):
            step.requeue_count += 1
            step.attempts = 0
            self.plan.steps.append(step)   # append to end
            return TransitionResult(event=TransitionEvent.REQUEUE)

        return self._complete_and_advance(step, revealed=True)

    async def record_follow_up(self, step: ExamStep, fu_result: FollowUpResult) -> TransitionResult:
        """Called after a follow-up has been LLM-graded. Transcribes
        to spike notes, advances to next follow-up or completes.
        """
        step.follow_up_results.append(fu_result)
        remaining = [
            fu for fu in step.follow_ups
            if fu not in [r.follow_up for r in step.follow_up_results]
        ]
        if remaining:
            return TransitionResult(
                event=TransitionEvent.ENTER_FOLLOW_UP,
                payload={"follow_up": remaining[0]},
            )
        return self._complete_and_advance(step)

    def _complete_and_advance(self, step: ExamStep, *, revealed: bool = False) -> TransitionResult:
        """Fire FSRS for the primary quiz result only. Never fires
        follow-ups (by type — FollowUpResult is not QuizResult).
        """
        if self.persist and step.final_result and step.final_result.grade:
            notes = self._compose_notes(step)
            # Spike.notes stores follow-up observations for next review
            asyncio.create_task(
                self.circuit.fire(
                    Spike(
                        neuron_id=step.neuron_id,
                        grade=step.final_result.grade,
                        notes=notes,
                    )
                )
            )
        self._history.append(step)
        self._current = None
        self._idx += 1
        return TransitionResult(event=TransitionEvent.ADVANCE)

    def _compose_notes(self, step: ExamStep) -> str | None:
        """Aggregate user notes + follow-up observations into
        spike.notes for future review context.
        """
        parts: list[str] = []
        if step.final_result and step.final_result.user_notes:
            parts.append(step.final_result.user_notes)
        for fu_result in step.follow_up_results:
            if fu_result.correctness < 0.7:
                parts.append(fu_result.note_for_next_review)
        return " | ".join(parts) if parts else None
```

## What moves where

| Component | Old location | New location |
|---|---|---|
| `Quiz` abstract base | `spikuit_core.quiz` | *deleted*, replaced by `spikuit_cli.quiz.BaseQuiz` (already in v0.6.2) |
| `Flashcard` (legacy) | `spikuit_core.quiz` | *deleted*, use `spikuit_cli.quiz.Flashcard` (already in v0.6.2) |
| `AutoQuiz` | `spikuit_core.quiz` | *deleted*, concept replaced by `FreeResponseQuiz` + `LLMGrader` |
| `TutorSession` | `spikuit_core.tutor` | `spikuit_cli.tutor.session` |
| `TutorState` | `spikuit_core.tutor` | *replaced by* `ExamStep` |
| *(new)* `ExamPlan` | — | `spikuit_cli.tutor.plan` |
| *(new)* `FollowUp`, `FollowUpResult` | — | `spikuit_cli.tutor.plan` |
| *(new)* `plan_exam()` | — | `spikuit_cli.tutor.builder` |
| *(new)* `FreeResponseQuiz` | — | `spikuit_cli.quiz.free_response` |
| *(new)* `LLMGrader` Protocol | — | `spikuit_cli.quiz.grader` |
| *(new)* `OneShotLLMGrader` impl | — | `spikuit_cli.quiz.graders.one_shot` |
| *(new)* `AgentLLMGrader` impl | — | `spikuit_agents.tutor.grader` |
| `QuizItem` (struct in models) | `spikuit_core.models` | **kept** (unused in v0.6.3, removed in v0.7+) |

`spikuit-core` ends up with zero references to quiz or tutor concepts
after v0.6.3. The `QuizItem` struct stays because removing it would
require a DB migration and the AMKB branch may touch `models.py`.

No v0.6.2 files move locations — only additions. `spikuit-cli` remains
usable standalone: Flashcards work without any grader, FreeResponseQuiz
with an injected `OneShotLLMGrader` (LM Studio / Ollama) works without
`spikuit-agents` installed.

## LLM grading path — `LLMGrader` Protocol

FreeResponseQuiz and FollowUp both need LLM grading. The Protocol lives
in `spikuit_cli.quiz.grader` so cli is self-sufficient:

```python
# spikuit_cli/quiz/grader.py
from typing import Protocol

class LLMGrader(Protocol):
    async def grade_free_response(
        self,
        *,
        prompt: str,
        canonical_answer: str,
        student_response: str,
        rubric: str | None = None,
    ) -> QuizResult: ...

    async def grade_follow_up(
        self,
        *,
        follow_up: FollowUp,
        student_response: str,
    ) -> FollowUpResult: ...

    async def generate_follow_up(
        self,
        *,
        neuron: Neuron,
        anchor: Neuron,
    ) -> FollowUp: ...
```

**Reference implementation** (`spikuit_cli.quiz.graders.one_shot.OneShotLLMGrader`):
takes `base_url`, `api_key`, `model` and makes one-shot chat completions
against any OpenAI-compatible endpoint (LM Studio, Ollama, OpenAI, etc.).
Reuses the existing `spikuit_core.embedder.OpenAICompat` dependency path
for consistency.

**Agent implementation** (`spikuit_agents.tutor.grader.AgentLLMGrader`):
implemented in Phase 4, delegates to Claude/GPT agent sub-skills for
richer rubric grading with retry and self-consistency checks. Satisfies
the same Protocol so users can swap between them with a single flag.

**No grader provided**: `TutorSession(grader=None)` causes
`FreeResponseQuiz.grade()` to fall back to `self_grade` semantics (like
Flashcard), keeping the whole code path testable without an LLM.

**CLI wiring**:
```bash
spkt quiz                           # self-grade, no LLM at all
spkt quiz --grader lmstudio \       # one-shot LM Studio grading
  --model gpt-oss-120b
spkt quiz --grader agent            # (requires spikuit-agents installed)
```

## Resolved design decisions

1. **Plan (data) / Session (interpreter) split** — confirmed. Keeps
   pedagogical policy declarative and testable.
2. **`FollowUpResult` as distinct type from `QuizResult`** — confirmed.
   Makes "follow-ups never fire FSRS" a type-level guarantee.
3. **FSRS write path** — *awaited*, not fire-and-forget. Swallowed
   errors are worse than a few ms of latency.
4. **`LLMGrader` Protocol location** — `spikuit_cli.quiz.grader`.
   Quiz types that need LLM grading live in cli alongside the Protocol,
   and any client (one-shot LLM, Agent, mock) can satisfy it.
