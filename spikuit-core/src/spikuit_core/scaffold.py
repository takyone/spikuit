"""Scaffold — compute scaffolding level from Brain state.

Determines how much support a learner needs for a given Neuron,
based on FSRS state, graph neighbors, and pressure.
Inspired by Vygotsky's Zone of Proximal Development.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fsrs import State

from .models import Scaffold, ScaffoldLevel

if TYPE_CHECKING:
    from .circuit import Circuit


def compute_scaffold(circuit: Circuit, neuron_id: str) -> Scaffold:
    """Compute scaffolding for a neuron based on Brain state.

    Returns a Scaffold with:
    - level: how much support to provide
    - context: strong neighbor IDs (scaffolding material)
    - gaps: weak prerequisite IDs (should study first)
    - hints: auto-generated hints from neighbors
    """
    card = circuit.get_card(neuron_id)
    if card is None:
        return Scaffold(level=ScaffoldLevel.FULL)

    # Determine level from FSRS state + stability
    level = _level_from_fsrs(card, circuit)

    # Find strong neighbors (scaffolding material) and weak prerequisites (gaps)
    context: list[str] = []
    gaps: list[str] = []

    # Check outgoing edges (things this neuron requires/extends)
    for neighbor_id in circuit.neighbors(neuron_id):
        neighbor_card = circuit.get_card(neighbor_id)
        if neighbor_card is None:
            gaps.append(neighbor_id)
            continue

        edge_data = circuit.graph[neuron_id][neighbor_id]
        edge_type = edge_data.get("type", "relates_to")

        if neighbor_card.state == State.Review and (neighbor_card.stability or 0) > 5.0:
            # Learner knows this well — useful as scaffolding context
            context.append(neighbor_id)
        elif edge_type == "requires":
            # This is a prerequisite and it's weak — it's a gap
            gaps.append(neighbor_id)

    # Check incoming edges (things that require this neuron)
    for pred_id in circuit.predecessors(neuron_id):
        pred_card = circuit.get_card(pred_id)
        if pred_card is not None and pred_card.state == State.Review and (pred_card.stability or 0) > 5.0:
            context.append(pred_id)

    return Scaffold(
        level=level,
        context=context,
        gaps=gaps,
    )


def _level_from_fsrs(card, circuit: Circuit) -> ScaffoldLevel:
    """Map FSRS card state to scaffold level."""
    stability = card.stability or 0.0

    if card.state == State.Learning:
        return ScaffoldLevel.FULL

    if card.state == State.Relearning:
        return ScaffoldLevel.GUIDED

    # State.Review — use stability to determine level
    if stability < 5.0:
        return ScaffoldLevel.GUIDED
    elif stability < 21.0:
        return ScaffoldLevel.MINIMAL
    else:
        return ScaffoldLevel.NONE
