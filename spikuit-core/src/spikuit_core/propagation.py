"""Spikuit propagation — APPNP spreading + LIF pressure + STDP edge updates.

This module implements the Graph Propagation Layer that sits on top of FSRS.
It determines "what to review alongside" via pressure, without touching
FSRS stability/difficulty.

Key algorithms:
- APPNP (Personalized PageRank): propagate activation from a fired neuron
- LIF (Leaky Integrate-and-Fire): pressure accumulates and decays over time
- STDP (Spike-Timing-Dependent Plasticity): strengthen/weaken edges based
  on temporal correlation between neighboring spikes
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import networkx as nx
import numpy as np

from .models import Grade, Plasticity


def compute_propagation(
    graph: nx.DiGraph,
    source_id: str,
    grade: Grade,
    plasticity: Plasticity,
) -> dict[str, float]:
    """Run APPNP propagation from a fired neuron, return pressure deltas.

    Args:
        graph: The circuit's NetworkX DiGraph.
        source_id: The neuron that was just reviewed.
        grade: The review grade (affects propagation strength).
        plasticity: Plasticity parameters.

    Returns:
        Dict of {neuron_id: pressure_delta} for all affected neurons.
        The source neuron is NOT included (it gets reset separately).
    """
    if source_id not in graph or graph.number_of_nodes() < 2:
        return {}

    # Grade → activation strength
    # MISS=0 (no positive propagation), WEAK=0.25, FIRE=0.5, STRONG=1.0
    activation_strength = _grade_to_activation(grade)
    if activation_strength <= 0.0:
        return {}

    nodes = list(graph.nodes)
    if len(nodes) < 2:
        return {}

    node_to_idx: dict[str, int] = {nid: i for i, nid in enumerate(nodes)}
    n = len(nodes)

    source_idx = node_to_idx.get(source_id)
    if source_idx is None:
        return {}

    # Build normalized adjacency matrix with self-loops (A_hat)
    # nx.to_numpy_array gives A[i,j] for edge i→j, but we need activation
    # to flow along outgoing edges: if A fires and A→B exists, B should
    # receive activation. Transpose so A_hat @ Z propagates forward.
    A = nx.to_numpy_array(graph, nodelist=nodes, weight="weight").T
    # Add self-loops
    A_tilde = A + np.eye(n)
    # Degree normalization: D^(-1/2) * A_tilde * D^(-1/2)
    D_tilde = np.diag(A_tilde.sum(axis=1))
    D_tilde_inv_sqrt = np.diag(
        np.where(D_tilde.diagonal() > 0, 1.0 / np.sqrt(D_tilde.diagonal()), 0.0)
    )
    A_hat: np.ndarray = D_tilde_inv_sqrt @ A_tilde @ D_tilde_inv_sqrt

    # Initial activation vector: only the source node
    H = np.zeros(n)
    H[source_idx] = activation_strength

    # APPNP power iteration
    alpha = plasticity.alpha
    Z = H.copy()
    for _ in range(plasticity.propagation_steps):
        Z = (1 - alpha) * (A_hat @ Z) + alpha * H

    # Convert to pressure deltas (exclude source)
    deltas: dict[str, float] = {}
    for i, nid in enumerate(nodes):
        if nid == source_id:
            continue
        if Z[i] > 1e-6:  # threshold to avoid noise
            deltas[nid] = float(Z[i])

    return deltas


def decay_all_pressure(
    graph: nx.DiGraph,
    now: datetime,
    plasticity: Plasticity,
) -> None:
    """Apply LIF leak to all neuron pressures.

    Pressure decays exponentially: u(t) = u * exp(-dt / tau_m)
    """
    tau_m = plasticity.tau_m

    for nid in graph.nodes:
        data = graph.nodes[nid]
        current_pressure: float = data.get("pressure", 0.0)
        if current_pressure <= 0.0:
            continue

        last_update_str: str | None = data.get("pressure_updated_at")
        if last_update_str is None:
            continue

        last_update = datetime.fromisoformat(last_update_str)
        dt_days = (now - last_update).total_seconds() / 86400.0
        if dt_days <= 0:
            continue

        decayed = current_pressure * math.exp(-dt_days / tau_m)
        if decayed < 1e-6:
            decayed = 0.0

        data["pressure"] = decayed
        data["pressure_updated_at"] = now.isoformat()


def compute_stdp(
    graph: nx.DiGraph,
    fired_id: str,
    grade: Grade,
    fired_at: datetime,
    plasticity: Plasticity,
) -> list[tuple[str, str, float, bool]]:
    """Compute STDP weight updates for edges adjacent to the fired neuron.

    For each edge connecting fired_id to a neighbor:
    - If neighbor fired recently (within tau_stdp), compute timing-dependent
      weight change using exponential STDP window.
    - Pre→post (LTP): Δw = +a_plus * exp(-|Δt| / tau_stdp)
    - Post→pre (LTD): Δw = -a_minus * exp(-|Δt| / tau_stdp)

    MISS grade does not trigger co-fire or LTP (only LTD if applicable).

    Returns:
        List of (pre, post, new_weight, is_co_fire) for each updated edge.
    """
    if fired_id not in graph:
        return []

    # MISS grade should not trigger any STDP
    if grade == Grade.MISS:
        return []

    tau = plasticity.tau_stdp
    a_plus = plasticity.a_plus
    a_minus = plasticity.a_minus
    w_floor = plasticity.weight_floor
    w_ceil = plasticity.weight_ceiling

    updates: list[tuple[str, str, float, bool]] = []

    # Check all edges involving fired_id (both as pre and post)
    # Predecessors: edges where neighbor → fired_id
    for neighbor_id in list(graph.predecessors(fired_id)):
        if neighbor_id == fired_id:
            continue
        neighbor_data = graph.nodes[neighbor_id]
        neighbor_last_fire = _get_last_fire_time(neighbor_data)
        if neighbor_last_fire is None:
            continue

        dt_days = (fired_at - neighbor_last_fire).total_seconds() / 86400.0
        if abs(dt_days) > tau:
            continue

        # Edge: neighbor → fired_id
        # neighbor fired before fired_id → LTP (pre before post)
        edge_data = graph[neighbor_id][fired_id]
        old_w = edge_data.get("weight", 0.5)

        if dt_days > 0:
            # neighbor fired first (pre before post) → LTP
            dw = a_plus * math.exp(-abs(dt_days) / tau)
        else:
            # fired_id fired first (post before pre — but this shouldn't happen
            # since dt > 0 means fired_at > neighbor_last_fire)
            dw = -a_minus * math.exp(-abs(dt_days) / tau)

        new_w = max(w_floor, min(w_ceil, old_w + dw))
        updates.append((neighbor_id, fired_id, new_w, True))

    # Successors: edges where fired_id → neighbor
    for neighbor_id in list(graph.successors(fired_id)):
        if neighbor_id == fired_id:
            continue
        neighbor_data = graph.nodes[neighbor_id]
        neighbor_last_fire = _get_last_fire_time(neighbor_data)
        if neighbor_last_fire is None:
            continue

        dt_days = (fired_at - neighbor_last_fire).total_seconds() / 86400.0
        if abs(dt_days) > tau:
            continue

        # Edge: fired_id → neighbor
        edge_data = graph[fired_id][neighbor_id]
        old_w = edge_data.get("weight", 0.5)

        if dt_days > 0:
            # neighbor fired before fired_id (post fired before pre) → LTD
            # Wait — fired_id is pre, neighbor is post.
            # neighbor fired first, then fired_id fired → post before pre → LTD
            dw = -a_minus * math.exp(-abs(dt_days) / tau)
        else:
            # fired_id fired first (pre before post) — but dt > 0 means
            # fired_at > neighbor_last_fire, so neighbor fired first
            dw = a_plus * math.exp(-abs(dt_days) / tau)

        new_w = max(w_floor, min(w_ceil, old_w + dw))
        updates.append((fired_id, neighbor_id, new_w, True))

    return updates


def _get_last_fire_time(node_data: dict) -> datetime | None:  # type: ignore[type-arg]
    """Get the last fire timestamp from node data."""
    ts = node_data.get("last_fired_at")
    if ts is None:
        return None
    if isinstance(ts, str):
        return datetime.fromisoformat(ts)
    return ts


def _grade_to_activation(grade: Grade) -> float:
    """Map Grade to propagation activation strength.

    MISS = 0.0 (failed review should not positively activate neighbors)
    WEAK = 0.25
    FIRE = 0.5
    STRONG = 1.0
    """
    return {
        Grade.MISS: 0.0,
        Grade.WEAK: 0.25,
        Grade.FIRE: 0.5,
        Grade.STRONG: 1.0,
    }[grade]
