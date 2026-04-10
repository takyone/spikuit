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
    """Types of synaptic connections between Neurons."""

    REQUIRES = "requires"
    EXTENDS = "extends"
    CONTRASTS = "contrasts"
    RELATES_TO = "relates_to"

    @property
    def is_bidirectional(self) -> bool:
        return self in (SynapseType.CONTRASTS, SynapseType.RELATES_TO)


class Grade(int, Enum):
    """Spike grade — maps to FSRS Rating."""

    MISS = 1      # 失火 (Again)
    WEAK = 2      # 弱発火 (Hard)
    FIRE = 3      # 発火 (Good)
    STRONG = 4    # 強発火 (Easy)


# ---------------------------------------------------------------------------
# Neuron
# ---------------------------------------------------------------------------


class Neuron(msgspec.Struct, kw_only=True):
    """A unit of knowledge — the fundamental node in a Circuit.

    Content is stored as Markdown with optional YAML-style frontmatter.
    Only minimal metadata is extracted into fields for indexing.
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
        """Create a Neuron from Markdown content, extracting frontmatter."""
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

    Bidirectional types (contrasts, relates_to) are stored as two Synapse
    objects — one in each direction. Weights may be asymmetric.
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
    circuit.fire() to trigger FSRS update + propagation.
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
    """Plasticity parameters — configurable per Circuit. Immutable."""

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
    """How much support the learner needs."""

    FULL = "full"          # New / struggling — max hints, context, easy questions
    GUIDED = "guided"      # Progressing — hints on request, some context
    MINIMAL = "minimal"    # Competent — harder questions, less hand-holding
    NONE = "none"          # Mastered — application / synthesis level


class Scaffold(msgspec.Struct, kw_only=True):
    """Scaffolding state computed from Brain data.

    Determines how much support a Learn session provides,
    based on FSRS state, graph context, and pressure.
    """

    level: ScaffoldLevel = ScaffoldLevel.FULL
    hints: list[str] = msgspec.field(default_factory=list)
    context: list[str] = msgspec.field(default_factory=list)   # strong neighbor IDs
    gaps: list[str] = msgspec.field(default_factory=list)      # weak prerequisite IDs


# ---------------------------------------------------------------------------
# Quiz models
# ---------------------------------------------------------------------------


class QuizRequest(msgspec.Struct, kw_only=True):
    """Input for quiz generation — what to ask and how."""

    primary: str                          # primary neuron ID
    supporting: list[str] = msgspec.field(default_factory=list)  # supporting neuron IDs
    scaffold: Scaffold = msgspec.field(default_factory=Scaffold)
    quiz_type: str | None = None          # "recall" | "recognition" | "application" | "synthesis" | None (auto)


class QuizItem(msgspec.Struct, kw_only=True):
    """A generated quiz question (filled by LLM or template)."""

    question: str
    answer: str
    hints: list[str] = msgspec.field(default_factory=list)
    grading_criteria: str = ""


class QuizResult(msgspec.Struct, kw_only=True):
    """Result of a quiz — per-neuron grades + overall."""

    grades: dict[str, Grade]              # neuron_id → Grade
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
