"""Spikuit Circuit — the public API for the knowledge graph engine.

Circuit is the main entry point for spikuit-core. It owns the database,
the in-memory NetworkX graph, and exposes all operations external layers
(Quiz, CLI, agents) need.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
from fsrs import Card, Rating, Scheduler

from .db import DEFAULT_DB_PATH, Database
from .models import Grade, Neuron, Plasticity, Spike, Synapse, SynapseType

# Grade → FSRS Rating mapping
_GRADE_TO_RATING: dict[Grade, Rating] = {
    Grade.MISS: Rating.Again,
    Grade.WEAK: Rating.Hard,
    Grade.FIRE: Rating.Good,
    Grade.STRONG: Rating.Easy,
}


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
        self._db: Database = Database(db_path)
        self._graph: nx.DiGraph = nx.DiGraph()
        self._scheduler: Scheduler = Scheduler()
        self._cards: dict[str, Card] = {}  # neuron_id → FSRS Card (in-memory cache)
        self.plasticity: Plasticity = plasticity or Plasticity()

    # -- Lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        """Connect to DB and load the graph + FSRS cards into memory."""
        await self._db.connect()
        await self._load_graph()
        await self._load_cards()

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
                s.pre, s.post,
                type=s.type.value, weight=s.weight, co_fires=s.co_fires,
            )

    async def _load_cards(self) -> None:
        """Load FSRS cards from DB into memory cache."""
        self._cards.clear()
        rows = await self._db.conn.execute_fetchall(
            "SELECT neuron_id, card_json FROM fsrs_state"
        )
        for row in rows:
            card = Card.from_json(row["card_json"])
            self._cards[row["neuron_id"]] = card

    # -- Neuron operations --------------------------------------------------

    async def add_neuron(self, neuron: Neuron) -> Neuron:
        """Add a Neuron to the circuit. Initializes FSRS card."""
        await self._db.insert_neuron(neuron)
        self._graph.add_node(neuron.id, type=neuron.type, domain=neuron.domain)

        # Initialize FSRS card
        card = Card()
        self._cards[neuron.id] = card
        await self._db.upsert_fsrs_card(neuron.id, card.to_json())

        return neuron

    async def get_neuron(self, neuron_id: str) -> Neuron | None:
        return await self._db.get_neuron(neuron_id)

    async def list_neurons(self, **kwargs: object) -> list[Neuron]:
        return await self._db.list_neurons(**kwargs)  # type: ignore[arg-type]

    async def update_neuron(self, neuron: Neuron) -> None:
        await self._db.update_neuron(neuron)
        if neuron.id in self._graph:
            self._graph.nodes[neuron.id]["type"] = neuron.type
            self._graph.nodes[neuron.id]["domain"] = neuron.domain

    async def remove_neuron(self, neuron_id: str) -> None:
        await self._db.delete_neuron(neuron_id)
        if neuron_id in self._graph:
            self._graph.remove_node(neuron_id)
        self._cards.pop(neuron_id, None)

    # -- Synapse operations -------------------------------------------------

    async def add_synapse(
        self,
        pre: str,
        post: str,
        type: SynapseType,
        weight: float = 0.5,
    ) -> list[Synapse]:
        """Add a Synapse. Bidirectional types auto-create the reverse edge."""
        if pre not in self._graph or post not in self._graph:
            raise ValueError(
                f"Both neurons must exist in the circuit. "
                f"pre={pre!r} exists={pre in self._graph}, "
                f"post={post!r} exists={post in self._graph}"
            )

        created: list[Synapse] = []

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

    async def fire(self, spike: Spike) -> Card:
        """Record a review event, update FSRS state, return updated Card.

        This is the single contact point for external layers (Quiz, CLI).
        """
        # 1. Record spike
        await self._db.insert_spike(spike)

        # 2. Get or create FSRS card
        card = self._cards.get(spike.neuron_id)
        if card is None:
            card = Card()

        # 3. Review with FSRS
        rating = _GRADE_TO_RATING[spike.grade]
        updated_card, _log = self._scheduler.review_card(
            card, rating, spike.fired_at,
        )

        # 4. Persist updated card
        self._cards[spike.neuron_id] = updated_card
        await self._db.upsert_fsrs_card(spike.neuron_id, updated_card.to_json())

        # TODO Step 2: LIF pressure update + APPNP propagation
        # TODO Step 3: STDP edge update + BCM homeostasis

        return updated_card

    # -- FSRS queries -------------------------------------------------------

    def get_card(self, neuron_id: str) -> Card | None:
        """Get the FSRS Card for a neuron (from in-memory cache)."""
        return self._cards.get(neuron_id)

    async def due_neurons(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
    ) -> list[str]:
        """Return neuron IDs that are due for review."""
        if now is None:
            now = datetime.now(timezone.utc)
        due: list[str] = []
        for neuron_id, card in self._cards.items():
            if card.due <= now:
                due.append(neuron_id)
                if len(due) >= limit:
                    break
        return due

    # -- Retrieve -----------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Neuron]:
        """Retrieve neurons matching a query.

        Currently: simple keyword match on content.
        Step 4 will add semantic search + graph-weighted scoring.
        """
        all_neurons = await self._db.list_neurons(limit=1000)
        query_lower = query.lower()
        scored: list[tuple[int, Neuron]] = []
        for n in all_neurons:
            content_lower = n.content.lower()
            keywords = query_lower.split()
            hits = sum(1 for kw in keywords if kw in content_lower)
            if hits > 0:
                scored.append((hits, n))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [n for _, n in scored[:limit]]

        if results:
            await self._db.log_retrieve(query, [n.id for n in results])

        return results

    # -- Ensemble -----------------------------------------------------------

    def ensemble(self, neuron_id: str, *, hops: int = 2) -> list[str]:
        """Get the N-hop neighborhood of a neuron."""
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

    async def stats(self) -> dict[str, object]:
        """Overview statistics."""
        neuron_count = await self._db.count_neurons()
        return {
            "neurons": neuron_count,
            "synapses": self._graph.number_of_edges(),
            "graph_density": nx.density(self._graph) if neuron_count > 1 else 0.0,
            "cards_loaded": len(self._cards),
        }
