"""Spikuit Core data models — Neuron, Synapse, Spike, Plasticity.

All models use msgspec.Struct for type safety and fast serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import msgspec


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SynapseType(str, Enum):
    """Types of synaptic connections between Neurons.

    Attributes:
        REQUIRES: Directed — A requires understanding B.
        EXTENDS: Directed — A extends B.
        CONTRASTS: Bidirectional — A contrasts with B.
        RELATES_TO: Bidirectional — general association.
    """

    REQUIRES = "requires"
    EXTENDS = "extends"
    CONTRASTS = "contrasts"
    RELATES_TO = "relates_to"

    @property
    def is_bidirectional(self) -> bool:
        """Whether this synapse type creates edges in both directions."""
        return self in (SynapseType.CONTRASTS, SynapseType.RELATES_TO)


class Grade(int, Enum):
    """Spike grade — maps to FSRS Rating.

    Attributes:
        MISS: Failed recall (FSRS Again).
        WEAK: Uncertain recall (FSRS Hard).
        FIRE: Correct recall (FSRS Good).
        STRONG: Perfect recall (FSRS Easy).
    """

    MISS = 1
    WEAK = 2
    FIRE = 3
    STRONG = 4


# ---------------------------------------------------------------------------
# Neuron
# ---------------------------------------------------------------------------


class Neuron(msgspec.Struct, kw_only=True):
    """A unit of knowledge — the fundamental node in a Circuit.

    Content is stored as Markdown with optional YAML-style frontmatter.
    Only minimal metadata is extracted into fields for indexing.

    Attributes:
        id: Unique identifier (auto-generated as ``n-<hex12>``).
        content: Markdown content, optionally with YAML frontmatter.
        type: Category tag (e.g. ``"concept"``, ``"fact"``, ``"procedure"``).
        domain: Knowledge domain (e.g. ``"math"``, ``"french"``).
        source: Origin URL or reference.
        created_at: UTC timestamp, auto-set on creation.
        updated_at: UTC timestamp, auto-set on creation and mutation.
    """

    id: str
    content: str
    type: str | None = None
    domain: str | None = None
    source: str | None = None
    created_at: datetime = msgspec.UNSET  # type: ignore[assignment]
    updated_at: datetime = msgspec.UNSET  # type: ignore[assignment]

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc)
        if self.created_at is msgspec.UNSET:
            self.created_at = now
        if self.updated_at is msgspec.UNSET:
            self.updated_at = now

    @classmethod
    def create(cls, content: str, **overrides: Any) -> Neuron:
        """Create a Neuron from Markdown content, extracting frontmatter.

        Generates a unique ID and parses YAML-style frontmatter for
        ``type``, ``domain``, and ``source`` fields. Explicit overrides
        take precedence over frontmatter values.

        Args:
            content: Markdown text, optionally starting with ``---`` frontmatter.
            **overrides: Field overrides (``id``, ``type``, ``domain``, ``source``).

        Returns:
            A new Neuron instance.
        """
        neuron_id = overrides.pop("id", f"n-{uuid4().hex[:12]}")
        fm = _parse_frontmatter(content)
        return cls(
            id=neuron_id,
            content=content,
            type=overrides.get("type") or fm.get("type"),
            domain=overrides.get("domain") or fm.get("domain"),
            source=overrides.get("source") or fm.get("source"),
        )


# ---------------------------------------------------------------------------
# Synapse
# ---------------------------------------------------------------------------


class Synapse(msgspec.Struct, kw_only=True):
    """A directed connection between two Neurons.

    Bidirectional types (``contrasts``, ``relates_to``) are stored as two
    Synapse objects — one in each direction. Weights may be asymmetric.

    Attributes:
        pre: Source neuron ID (pre-synaptic).
        post: Target neuron ID (post-synaptic).
        type: Connection semantics (see [`SynapseType`][spikuit_core.SynapseType]).
        weight: Edge strength, updated by STDP (range: ``[weight_floor, weight_ceiling]``).
        co_fires: Number of times both endpoints fired within ``tau_stdp``.
        last_co_fire: Timestamp of the most recent co-fire event.
        created_at: UTC timestamp, auto-set on creation.
        updated_at: UTC timestamp, auto-set on creation and mutation.
    """

    pre: str
    post: str
    type: SynapseType
    weight: float = 0.5
    co_fires: int = 0
    last_co_fire: datetime | None = None
    created_at: datetime = msgspec.UNSET  # type: ignore[assignment]
    updated_at: datetime = msgspec.UNSET  # type: ignore[assignment]

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc)
        if self.created_at is msgspec.UNSET:
            self.created_at = now
        if self.updated_at is msgspec.UNSET:
            self.updated_at = now


# ---------------------------------------------------------------------------
# Spike
# ---------------------------------------------------------------------------


class Spike(msgspec.Struct, kw_only=True):
    """A review event — an action potential in the Circuit.

    Created by external layers (Quiz, CLI, etc.) and fed into
    [`Circuit.fire()`][spikuit_core.Circuit.fire] to trigger
    FSRS update + propagation.

    Attributes:
        neuron_id: The neuron being reviewed.
        grade: Review quality (see [`Grade`][spikuit_core.Grade]).
        fired_at: UTC timestamp, auto-set to now.
        session_id: Optional session identifier for grouping spikes.
    """

    neuron_id: str
    grade: Grade
    fired_at: datetime = msgspec.UNSET  # type: ignore[assignment]
    session_id: str | None = None

    def __post_init__(self) -> None:
        if self.fired_at is msgspec.UNSET:
            self.fired_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Plasticity
# ---------------------------------------------------------------------------


class Plasticity(msgspec.Struct, kw_only=True, frozen=True):
    """Tunable learning parameters — configurable per Circuit. Immutable.

    Controls how activation propagates, how edges strengthen/weaken,
    and how pressure accumulates and decays.

    Attributes:
        alpha: APPNP teleport probability (higher = more local).
        propagation_steps: APPNP power-iteration steps.
        tau_stdp: STDP time window in days.
        a_plus: STDP LTP amplitude (pre-before-post strengthening).
        a_minus: STDP LTD amplitude (post-before-pre weakening).
        tau_m: LIF membrane time constant in days (pressure decay rate).
        pressure_threshold: LIF pressure threshold for spontaneous review.
        pressure_rest: LIF resting pressure.
        pressure_reset: Pressure value after a neuron fires.
        theta_pro: STC promotion threshold (co-fire count).
        schema_factor: Bonus factor for schema-connected neurons.
        weight_floor: Minimum allowed edge weight.
        weight_ceiling: Maximum allowed edge weight.
    """

    # APPNP propagation
    alpha: float = 0.15
    propagation_steps: int = 5

    # STDP
    tau_stdp: float = 7.0
    a_plus: float = 0.03
    a_minus: float = 0.036

    # LIF
    tau_m: float = 14.0
    pressure_threshold: float = 0.8
    pressure_rest: float = 0.0
    pressure_reset: float = 0.1

    # STC
    theta_pro: int = 3

    # Schema bonus
    schema_factor: float = 0.2

    # Edge weight bounds
    weight_floor: float = 0.05
    weight_ceiling: float = 1.0


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------


class ScaffoldLevel(str, Enum):
    """How much support the learner needs (ZPD-inspired).

    Attributes:
        FULL: New or struggling — max hints, context, easy questions.
        GUIDED: Progressing — hints on request, some context.
        MINIMAL: Competent — harder questions, less hand-holding.
        NONE: Mastered — application / synthesis level.
    """

    FULL = "full"
    GUIDED = "guided"
    MINIMAL = "minimal"
    NONE = "none"


class Scaffold(msgspec.Struct, kw_only=True):
    """Scaffolding state computed from Brain data.

    Determines how much support a Learn session provides,
    based on FSRS state, graph context, and pressure.

    Attributes:
        level: Current support level.
        hints: Auto-generated hint strings.
        context: IDs of strong neighbors (scaffolding material).
        gaps: IDs of weak prerequisites (should study first).
    """

    level: ScaffoldLevel = ScaffoldLevel.FULL
    hints: list[str] = msgspec.field(default_factory=list)
    context: list[str] = msgspec.field(default_factory=list)
    gaps: list[str] = msgspec.field(default_factory=list)


# ---------------------------------------------------------------------------
# Quiz models
# ---------------------------------------------------------------------------


class QuizRequest(msgspec.Struct, kw_only=True):
    """Input for quiz generation — what to ask and how.

    Attributes:
        primary: Primary neuron ID to quiz on.
        supporting: Supporting neuron IDs for context.
        scaffold: Scaffolding state for difficulty adaptation.
        quiz_type: Question style — ``"recall"``, ``"recognition"``,
            ``"application"``, ``"synthesis"``, or ``None`` for auto.
    """

    primary: str
    supporting: list[str] = msgspec.field(default_factory=list)
    scaffold: Scaffold = msgspec.field(default_factory=Scaffold)
    quiz_type: str | None = None


class QuizItem(msgspec.Struct, kw_only=True):
    """A generated quiz question (filled by LLM or template).

    Attributes:
        question: The question text.
        answer: The expected answer.
        hints: Progressive hints (reveal one at a time).
        grading_criteria: Free-text criteria for LLM-based grading.
    """

    question: str
    answer: str
    hints: list[str] = msgspec.field(default_factory=list)
    grading_criteria: str = ""


class QuizResult(msgspec.Struct, kw_only=True):
    """Result of a quiz — per-neuron grades + overall.

    Attributes:
        grades: Mapping of neuron ID to grade.
        overall: Aggregate grade for the quiz.
    """

    grades: dict[str, Grade]
    overall: Grade


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML-like frontmatter from Markdown content.

    Uses a lightweight parser (no PyYAML dependency) for simple key: value pairs.
    """
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    result: dict[str, Any] = {}
    for line in parts[1].strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        if value:
            result[key.strip()] = value
    return result
