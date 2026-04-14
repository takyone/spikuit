"""Spikuit ↔ AMKB type codecs.

Scaffolding only — method bodies are filled in by task #12. See design
doc §3 (Node mapping) and §4 (Edge mapping) for the target behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import amkb
    from spikuit_core import Neuron, Source, Synapse


__all__ = [
    "neuron_to_node",
    "source_to_node",
    "synapse_to_edge",
    "edge_ref_for_synapse",
]


def neuron_to_node(neuron: "Neuron") -> "amkb.Node":
    raise NotImplementedError("filled in by task #12")


def source_to_node(source: "Source") -> "amkb.Node":
    raise NotImplementedError("filled in by task #12")


def synapse_to_edge(synapse: "Synapse") -> "amkb.Edge":
    raise NotImplementedError("filled in by task #12")


def edge_ref_for_synapse(synapse: "Synapse") -> "amkb.EdgeRef":
    raise NotImplementedError("filled in by task #12")
