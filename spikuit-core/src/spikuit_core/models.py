"""Spikuit Core data models — Neuron, Synapse, Spike, Plasticity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Self
from uuid import uuid4

import yaml


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SynapseType(str, Enum):
    """Types of synaptic connections between Neurons."""

    REQUIRES = "requires"       # pre requires post as prerequisite
    EXTENDS = "extends"         # pre extends/builds upon post
    CONTRASTS = "contrasts"     # bidirectional: comparison targets
    RELATES_TO = "relates_to"   # bidirectional: weak association

    @property
    def is_bidirectional(self) -> bool:
        return self in (SynapseType.CONTRASTS, SynapseType.RELATES_TO)


class Grade(int, Enum):
    """Spike grade — maps to FSRS rating."""

    MISS = 1     # 失火 (Again)
    WEAK = 2     # 弱発火 (Hard)
    FIRE = 3     # 発火 (Good)
    STRONG = 4   # 強発火 (Easy)


# ---------------------------------------------------------------------------
# Neuron
# ---------------------------------------------------------------------------

@dataclass
class Neuron:
    """A unit of knowledge — the fundamental node in a Circuit.

    Content is stored as Markdown with YAML frontmatter.
    Only minimal metadata is extracted into fields for indexing.
    """

    id: str
    content: str                        # Markdown body (including frontmatter)
    type: str | None = None             # extracted from frontmatter
    domain: str | None = None           # extracted from frontmatter
    source: str | None = None           # extracted from frontmatter
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(cls, content: str, **overrides) -> Self:
        """Create a Neuron from Markdown content, extracting frontmatter."""
        neuron_id = overrides.pop("id", f"n-{uuid4().hex[:12]}")
        fm = _parse_frontmatter(content)
        return cls(
            id=neuron_id,
            content=content,
            type=overrides.get("type") or fm.get("type"),
            domain=overrides.get("domain") or fm.get("domain"),
            source=overrides.get("source") or fm.get("source"),
            created_at=overrides.get("created_at", datetime.now(timezone.utc)),
            updated_at=overrides.get("updated_at", datetime.now(timezone.utc)),
        )


# ---------------------------------------------------------------------------
# Synapse
# ---------------------------------------------------------------------------

@dataclass
class Synapse:
    """A directed connection between two Neurons.

    Bidirectional types (contrasts, relates_to) are stored as two Synapse
    objects — one in each direction. Weights may be asymmetric.
    """

    pre: str                            # presynaptic neuron ID
    post: str                           # postsynaptic neuron ID
    type: SynapseType
    weight: float = 0.5                 # synaptic strength [0.0, 1.0]
    co_fires: int = 0                   # co-activation count
    last_co_fire: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Spike
# ---------------------------------------------------------------------------

@dataclass
class Spike:
    """A review event — an action potential in the Circuit.

    Created by external layers (Quiz, CLI, etc.) and fed into
    circuit.fire() to trigger FSRS update + propagation.
    """

    neuron_id: str
    grade: Grade
    fired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str | None = None       # optional: from QuizSession


# ---------------------------------------------------------------------------
# Plasticity
# ---------------------------------------------------------------------------

@dataclass
class Plasticity:
    """Plasticity parameters — configurable per Circuit."""

    # APPNP propagation
    alpha: float = 0.15                 # teleport probability
    propagation_steps: int = 5          # K iterations

    # STDP (Spike-Timing-Dependent Plasticity)
    tau_stdp: float = 7.0               # timing window (days)
    a_plus: float = 0.03                # LTP learning rate
    a_minus: float = 0.036              # LTD learning rate

    # BCM (homeostasis)
    # theta_M is computed per-neuron, not a global parameter

    # LIF (Leaky Integrate-and-Fire)
    tau_m: float = 14.0                 # membrane time constant (days)
    pressure_threshold: float = 0.8     # firing threshold for review suggestion
    pressure_rest: float = 0.0          # resting potential
    pressure_reset: float = 0.1         # post-fire reset value

    # STC (Synaptic Tagging and Capture)
    theta_pro: int = 3                  # related neurons needed for consolidation

    # Schema bonus
    schema_factor: float = 0.2

    # Edge weight bounds
    weight_floor: float = 0.05
    weight_ceiling: float = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from Markdown content."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
