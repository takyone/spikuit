"""Command modules for the spkt CLI."""

from .community import community_app
from .domain import domain_app
from .neuron import neuron_app
from .skills import skills_app
from .source import source_app
from .synapse import synapse_app

__all__ = [
    "community_app",
    "domain_app",
    "neuron_app",
    "skills_app",
    "source_app",
    "synapse_app",
]
