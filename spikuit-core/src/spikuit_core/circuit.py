"""Spikuit Circuit — the public API for the knowledge graph engine.

Circuit is the main entry point for spikuit-core. It owns the database,
the in-memory NetworkX graph, and exposes all operations external layers
(Quiz, CLI, agents) need.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from .db import DEFAULT_DB_PATH, Database
from .models import Grade, Neuron, Plasticity, Spike, Synapse, SynapseType


class Circuit:
    """A neural circuit — the full knowledge graph with persistence.

    Usage::

        circuit = Circuit()
        await circuit.connect()

        neuron = Neuron.create("# functor\\n\\n圏の間の写像。")
        await circuit.add_neuron(neuron)

        spike = Spike(neuron_id=neuron.id, grade=Grade.FIRE)
        await circuit.fire(spike)

        await circuit.close()
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        plasticity: Plasticity | None = None,
    ) -> None:
        self._db = Database(db_path)
        self._graph = nx.DiGraph()
        self.plasticity = plasticity or Plasticity()

    # -- Lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        """Connect to DB and load the graph into memory."""
        await self._db.connect()
        await self._load_graph()

    async def close(self) -> None:
        await self._db.close()

    async def _load_graph(self) -> None:
        """Load all neurons (as nodes) and synapses (as edges) into NetworkX."""
        self._graph.clear()

        neurons = await self._db.list_neurons(limit=100_000)
        for n in neurons:
            self._graph.add_node(n.id, type=n.type, domain=n.domain)

        synapses = await self._db.get_all_synapses()
        for s in synapses:
            self._graph.add_edge(
                s.pre,
                s.post,
                type=s.type.value,
                weight=s.weight,
                co_fires=s.co_fires,
            )

    # -- Neuron operations --------------------------------------------------

    async def add_neuron(self, neuron: Neuron) -> Neuron:
        """Add a Neuron to the circuit."""
        await self._db.insert_neuron(neuron)
        self._graph.add_node(neuron.id, type=neuron.type, domain=neuron.domain)
        return neuron

    async def get_neuron(self, neuron_id: str) -> Neuron | None:
        return await self._db.get_neuron(neuron_id)

    async def list_neurons(self, **kwargs) -> list[Neuron]:
        return await self._db.list_neurons(**kwargs)

    async def update_neuron(self, neuron: Neuron) -> None:
        await self._db.update_neuron(neuron)
        # Update graph node attributes
        if neuron.id in self._graph:
            self._graph.nodes[neuron.id]["type"] = neuron.type
            self._graph.nodes[neuron.id]["domain"] = neuron.domain

    async def remove_neuron(self, neuron_id: str) -> None:
        await self._db.delete_neuron(neuron_id)
        if neuron_id in self._graph:
            self._graph.remove_node(neuron_id)

    # -- Synapse operations -------------------------------------------------

    async def add_synapse(
        self,
        pre: str,
        post: str,
        type: SynapseType,
        weight: float = 0.5,
    ) -> list[Synapse]:
        """Add a Synapse. Bidirectional types auto-create the reverse edge.

        Returns all created Synapses.
        """
        if pre not in self._graph or post not in self._graph:
            raise ValueError(
                f"Both neurons must exist in the circuit. "
                f"pre={pre!r} exists={pre in self._graph}, "
                f"post={post!r} exists={post in self._graph}"
            )

        created = []
        synapse = Synapse(pre=pre, post=post, type=type, weight=weight)
        await self._db.insert_synapse(synapse)
        self._graph.add_edge(
            pre, post, type=type.value, weight=weight, co_fires=0,
        )
        created.append(synapse)

        if type.is_bidirectional:
            reverse = Synapse(pre=post, post=pre, type=type, weight=weight)
            await self._db.insert_synapse(reverse)
            self._graph.add_edge(
                post, pre, type=type.value, weight=weight, co_fires=0,
            )
            created.append(reverse)

        return created

    async def get_synapse(
        self, pre: str, post: str, type: SynapseType
    ) -> Synapse | None:
        return await self._db.get_synapse(pre, post, type)

    async def remove_synapse(
        self, pre: str, post: str, type: SynapseType
    ) -> None:
        await self._db.delete_synapse(pre, post, type)
        if self._graph.has_edge(pre, post):
            self._graph.remove_edge(pre, post)

        if type.is_bidirectional:
            await self._db.delete_synapse(post, pre, type)
            if self._graph.has_edge(post, pre):
                self._graph.remove_edge(post, pre)

    # -- Spike (fire) -------------------------------------------------------

    async def fire(self, spike: Spike) -> None:
        """Record a review event and trigger propagation.

        This is the single contact point for external layers (Quiz, CLI).
        Currently Step 0: just records the spike. Propagation comes in Step 2+.
        """
        await self._db.insert_spike(spike)
        # TODO Step 1: FSRS state update
        # TODO Step 2: LIF pressure update + APPNP propagation
        # TODO Step 3: STDP edge update + BCM homeostasis

    # -- Retrieve -----------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Neuron]:
        """Retrieve neurons matching a query.

        Currently Step 0: simple keyword match on content.
        Step 4 will add semantic search + graph-weighted scoring.
        """
        # Simple keyword search for now
        all_neurons = await self._db.list_neurons(limit=1000)
        query_lower = query.lower()
        scored = []
        for n in all_neurons:
            content_lower = n.content.lower()
            # Count keyword hits
            keywords = query_lower.split()
            hits = sum(1 for kw in keywords if kw in content_lower)
            if hits > 0:
                scored.append((hits, n))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [n for _, n in scored[:limit]]

        # Log the retrieve
        if results:
            await self._db.log_retrieve(query, [n.id for n in results])

        # TODO Step 2: update pressure on retrieved neurons (priming)
        # TODO Step 4: semantic similarity + retrieve_score formula

        return results

    # -- Ensemble -----------------------------------------------------------

    def ensemble(self, neuron_id: str, *, hops: int = 2) -> list[str]:
        """Get the N-hop neighborhood of a neuron.

        Returns neuron IDs within `hops` distance in the graph.
        """
        if neuron_id not in self._graph:
            return []
        subgraph = nx.ego_graph(self._graph, neuron_id, radius=hops)
        return [nid for nid in subgraph.nodes if nid != neuron_id]

    # -- Graph introspection ------------------------------------------------

    def neighbors(self, neuron_id: str) -> list[str]:
        """Direct successors (outgoing synapses)."""
        if neuron_id not in self._graph:
            return []
        return list(self._graph.successors(neuron_id))

    def predecessors(self, neuron_id: str) -> list[str]:
        """Direct predecessors (incoming synapses)."""
        if neuron_id not in self._graph:
            return []
        return list(self._graph.predecessors(neuron_id))

    @property
    def neuron_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def synapse_count(self) -> int:
        return self._graph.number_of_edges()

    @property
    def graph(self) -> nx.DiGraph:
        """Direct access to the NetworkX graph (read-only use)."""
        return self._graph

    # -- Stats --------------------------------------------------------------

    async def stats(self) -> dict:
        """Overview statistics."""
        neuron_count = await self._db.count_neurons()
        return {
            "neurons": neuron_count,
            "synapses": self._graph.number_of_edges(),
            "graph_density": nx.density(self._graph) if neuron_count > 1 else 0.0,
        }
