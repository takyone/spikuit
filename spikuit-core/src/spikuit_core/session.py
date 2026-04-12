"""Session — interaction modes for the Brain.

A Session wraps a Circuit and provides a specific interaction pattern.
The Brain (Circuit) is the universal backend; Sessions are the modes:
- QABotSession: RAG chat with retrieval feedback optimization
- IngestSession: Conversational knowledge ingestion / curation
- ReviewSession: Spaced repetition (wraps Quiz protocol) — planned

Sessions can be persistent (retrieval_boost committed on close) or
ephemeral (weights discarded on close).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .embedder import Embedder, vec_to_blob
from .models import Neuron, Source, Synapse, SynapseType

if TYPE_CHECKING:
    from .circuit import Circuit


@dataclass
class RetrievalResult:
    """A single retrieval result with metadata.

    Attributes:
        neuron_id: The matched neuron's ID.
        score: Relevance score (higher = better).
        content: Neuron content (Markdown).
        context_ids: IDs of ensemble neighbors (N-hop context).
        sources: Source records attached to this neuron (for citation).
    """

    neuron_id: str
    score: float
    content: str
    context_ids: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)


class Session(ABC):
    """Abstract base for Brain interaction sessions.

    All sessions wrap a [`Circuit`][spikuit_core.Circuit] and can be
    either **persistent** (changes committed on close) or **ephemeral**
    (changes discarded on close).

    Args:
        circuit: The Circuit to interact with.
        persist: Whether to commit changes on close.
    """

    def __init__(
        self,
        circuit: Circuit,
        *,
        persist: bool = True,
    ) -> None:
        self.circuit = circuit
        self.persist = persist

    @abstractmethod
    async def close(self) -> None:
        """End the session. Persistent sessions commit weights."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset session state without closing."""
        ...


class QABotSession(Session):
    """RAG chat session with self-optimizing retrieval.

    Provides intelligent retrieval that improves during the conversation:

    - **Negative feedback**: follow-up similar queries penalize prior results
    - **Deduplication**: already-returned neurons are excluded
    - **Accept**: explicit positive feedback boosts neurons
    - **Persistent/ephemeral**: choose whether to commit boosts on close

    Example:
        ```python
        session = QABotSession(circuit, persist=True)
        results = await session.ask("What is a functor?")
        await session.accept(["n-abc123"])  # this one was helpful
        results = await session.ask("functor examples?")  # auto-penalizes prior
        await session.close()  # commits boosts if persistent
        ```

    Args:
        circuit: The Circuit (must have an embedder configured).
        persist: Commit retrieval boosts on close.
        learning_rate: Feedback strength (default ``0.1``).
        exclude_seen: Skip already-returned neurons (default ``True``).
    """

    def __init__(
        self,
        circuit: Circuit,
        *,
        persist: bool = True,
        learning_rate: float = 0.1,
        exclude_seen: bool = True,
    ) -> None:
        super().__init__(circuit, persist=persist)
        self._lr = learning_rate
        self._exclude_seen = exclude_seen
        self._prior_query_vecs: list[list[float]] = []
        self._prior_result_ids: list[set[str]] = []  # per-turn result sets
        self._all_returned: set[str] = set()
        self._accepted: set[str] = set()
        self._boost_deltas: dict[str, float] = {}  # accumulated during session

    @property
    def embedder(self) -> Embedder:
        if self.circuit._embedder is None:
            raise RuntimeError("QABotSession requires a Circuit with an embedder")
        return self.circuit._embedder

    async def ask(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Ask a question. Returns scored, deduplicated results.

        Automatically applies negative feedback if this is a follow-up
        to a similar prior query (implicit signal that prior results
        were insufficient).
        """
        query_vec = await self.embedder.embed(query)

        # Apply negative feedback from prior turns
        if self._prior_query_vecs:
            self._apply_negative_feedback(query_vec)

        # Retrieve with graph-weighted scoring (includes retrieval_boost)
        # Request extra candidates to compensate for dedup filtering
        request_limit = limit * 3 if self._exclude_seen else limit
        candidates = await self.circuit.retrieve(query, limit=request_limit)

        # Dedup: exclude already-returned neurons
        if self._exclude_seen:
            candidates = [n for n in candidates if n.id not in self._all_returned]

        results: list[RetrievalResult] = []
        turn_ids: set[str] = set()
        for n in candidates[:limit]:
            context_ids = self.circuit.ensemble(n.id, hops=1)
            sources = await self.circuit.get_sources_for_neuron(n.id)
            results.append(RetrievalResult(
                neuron_id=n.id,
                score=0.0,  # score is internal to retrieve()
                content=n.content,
                context_ids=context_ids,
                sources=sources,
            ))
            turn_ids.add(n.id)

        # Record this turn
        self._prior_query_vecs.append(query_vec)
        self._prior_result_ids.append(turn_ids)
        self._all_returned.update(turn_ids)

        return results

    def _apply_negative_feedback(self, query_vec: list[float]) -> None:
        """Penalize prior results based on similarity to current query.

        If the user/agent asks a similar follow-up, it means prior results
        weren't sufficient. Penalty is proportional to query overlap.
        """
        for i, prior_vec in enumerate(self._prior_query_vecs):
            overlap = _cosine_sim(query_vec, prior_vec)
            if overlap < 0.1:
                continue  # unrelated query, no penalty

            prior_ids = self._prior_result_ids[i]
            for nid in prior_ids:
                if nid in self._accepted:
                    continue  # don't penalize accepted neurons

                current_boost = self.circuit.get_retrieval_boost(nid)
                # Diminishing penalty: less impact when already penalized
                penalty = self._lr * overlap / (1.0 + abs(current_boost))
                new_boost = current_boost - penalty
                self.circuit.set_retrieval_boost(nid, new_boost)
                self._boost_deltas[nid] = new_boost

    async def accept(self, neuron_ids: list[str]) -> None:
        """Mark neurons as helpful (positive feedback).

        Boosts retrieval_boost with diminishing returns.
        """
        for nid in neuron_ids:
            self._accepted.add(nid)
            current_boost = self.circuit.get_retrieval_boost(nid)
            # Diminishing returns: less boost when already boosted
            gain = self._lr / (1.0 + current_boost)
            new_boost = current_boost + gain
            self.circuit.set_retrieval_boost(nid, new_boost)
            self._boost_deltas[nid] = new_boost

    def reset(self) -> None:
        """Reset session state (new topic). Does NOT reset boosts."""
        self._prior_query_vecs.clear()
        self._prior_result_ids.clear()
        self._all_returned.clear()
        self._accepted.clear()

    async def close(self) -> None:
        """End the session. Commits boosts if persistent."""
        if self.persist and self._boost_deltas:
            await self.circuit.commit_retrieval_boosts()
        self.reset()

    @property
    def turns(self) -> int:
        """Number of ask() calls in this session."""
        return len(self._prior_query_vecs)

    @property
    def stats(self) -> dict:
        """Session statistics."""
        return {
            "turns": self.turns,
            "total_returned": len(self._all_returned),
            "accepted": len(self._accepted),
            "boost_updates": len(self._boost_deltas),
            "persist": self.persist,
        }


class IngestSession(Session):
    """Conversational knowledge curation session.

    Lets a user (or agent) build and refine the knowledge graph through
    dialogue: add neurons, discover related concepts, create synapses,
    and merge duplicates. This is how **conversational RAG curation**
    works — the conversation directly improves retrieval quality by
    curating the graph structure.

    Example:
        ```python
        session = IngestSession(circuit)
        n, related = await session.ingest(
            "# Functor\\n\\nA mapping between categories.",
            type="concept",
        )
        if related:
            await session.relate(n.id, related[0].id, SynapseType.REQUIRES)
        print(session.stats)
        await session.close()
        ```

    Args:
        circuit: The Circuit to curate.
        persist: Commit retrieval boosts on close.
        auto_relate: Automatically search for related neurons on ingest.
        auto_relate_limit: Max related neurons returned by ingest.
    """

    def __init__(
        self,
        circuit: Circuit,
        *,
        persist: bool = True,
        auto_relate: bool = True,
        auto_relate_limit: int = 5,
    ) -> None:
        super().__init__(circuit, persist=persist)
        self._auto_relate = auto_relate
        self._auto_relate_limit = auto_relate_limit
        self._added: list[str] = []
        self._linked: list[tuple[str, str, SynapseType]] = []
        self._merged: list[tuple[list[str], str]] = []

    async def ingest(
        self,
        content: str,
        *,
        type: str | None = None,
        domain: str | None = None,
        source: str | None = None,
        source_meta: Source | None = None,
        id: str | None = None,
    ) -> tuple[Neuron, list[Neuron]]:
        """Add a neuron and discover related existing knowledge.

        Creates the neuron, auto-embeds it (if an embedder is configured),
        and searches for related neurons via graph-weighted retrieval.

        When ``source_meta`` is provided, the source is deduplicated by URL,
        created if new, and attached to the new neuron.

        Args:
            content: Markdown content for the new neuron.
            type: Category tag (e.g. ``"concept"``).
            domain: Knowledge domain (e.g. ``"math"``).
            source: Origin URL or reference (legacy string field).
            source_meta: Structured Source for citation tracking.
            id: Custom neuron ID (auto-generated if ``None``).

        Returns:
            Tuple of ``(new_neuron, related_neurons)``. Use
            [`relate()`][spikuit_core.IngestSession.relate] to connect them.
        """
        kwargs: dict[str, object] = {}
        if type is not None:
            kwargs["type"] = type
        if domain is not None:
            kwargs["domain"] = domain
        if source is not None:
            kwargs["source"] = source
        if id is not None:
            kwargs["id"] = id

        neuron = Neuron.create(content, **kwargs)
        await self.circuit.add_neuron(neuron)
        self._added.append(neuron.id)

        # Attach structured source if provided
        if source_meta is not None:
            # Dedup by URL
            existing = None
            if source_meta.url:
                existing = await self.circuit.find_source_by_url(source_meta.url)
            if existing is not None:
                await self.circuit.attach_source(neuron.id, existing.id)
            else:
                await self.circuit.add_source(source_meta)
                await self.circuit.attach_source(neuron.id, source_meta.id)

        # Auto-discover related neurons
        related: list[Neuron] = []
        if self._auto_relate:
            related = await self.circuit.retrieve(
                content[:200], limit=self._auto_relate_limit,
            )
            # Exclude the neuron we just added
            related = [n for n in related if n.id != neuron.id]

        return neuron, related

    async def relate(
        self,
        a: str,
        b: str,
        type: SynapseType = SynapseType.RELATES_TO,
        *,
        weight: float = 0.5,
    ) -> list[Synapse]:
        """Create or strengthen a synapse between two neurons.

        If the synapse already exists, its weight is increased by ``0.1``
        (capped at ``plasticity.weight_ceiling``). Bidirectional types
        create edges in both directions.

        Args:
            a: Source neuron ID.
            b: Target neuron ID.
            type: Connection semantics (default ``relates_to``).
            weight: Initial weight for new synapses.

        Returns:
            List of created or updated synapses.
        """
        existing = await self.circuit.get_synapse(a, b, type)
        if existing is not None:
            # Strengthen existing synapse
            ceiling = self.circuit.plasticity.weight_ceiling
            new_weight = min(existing.weight + 0.1, ceiling)
            updated = Synapse(
                pre=existing.pre,
                post=existing.post,
                type=existing.type,
                weight=new_weight,
                co_fires=existing.co_fires,
                last_co_fire=existing.last_co_fire,
            )
            await self.circuit._db.update_synapse(updated)
            # Update in-memory graph
            if self.circuit._graph.has_edge(a, b):
                self.circuit._graph[a][b]["weight"] = new_weight
            self._linked.append((a, b, type))
            return [updated]

        synapses = await self.circuit.add_synapse(a, b, type, weight=weight)
        self._linked.append((a, b, type))
        return synapses

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Neuron]:
        """Search existing knowledge using graph-weighted retrieval.

        Args:
            query: Search text.
            limit: Maximum results.

        Returns:
            Matching neurons sorted by relevance.
        """
        return await self.circuit.retrieve(query, limit=limit)

    async def merge(
        self,
        source_ids: list[str],
        into_id: str,
    ) -> Neuron:
        """Merge source neurons into a target neuron.

        Transfers all synapses from source neurons to the target,
        appends their content with ``---`` separators, then removes
        the source neurons.

        Args:
            source_ids: IDs of neurons to merge (will be deleted).
            into_id: ID of the target neuron (will be preserved).

        Returns:
            The updated target neuron with merged content.

        Raises:
            ValueError: If the target neuron does not exist.
        """
        target = await self.circuit.get_neuron(into_id)
        if target is None:
            raise ValueError(f"Target neuron {into_id!r} not found")

        # Collect content and synapses from sources
        extra_content: list[str] = []
        for sid in source_ids:
            if sid == into_id:
                continue
            source = await self.circuit.get_neuron(sid)
            if source is None:
                continue
            extra_content.append(source.content)

            # Transfer outgoing synapses
            for neighbor_id in list(self.circuit.neighbors(sid)):
                if neighbor_id == into_id:
                    continue
                edge_data = self.circuit._graph[sid][neighbor_id]
                syn_type = SynapseType(edge_data["type"])
                # Only add if not already connected
                if not self.circuit._graph.has_edge(into_id, neighbor_id):
                    await self.circuit.add_synapse(
                        into_id, neighbor_id, syn_type,
                        weight=edge_data.get("weight", 0.5),
                    )

            # Transfer incoming synapses
            for pred_id in list(self.circuit.predecessors(sid)):
                if pred_id == into_id:
                    continue
                edge_data = self.circuit._graph[pred_id][sid]
                syn_type = SynapseType(edge_data["type"])
                if not self.circuit._graph.has_edge(pred_id, into_id):
                    await self.circuit.add_synapse(
                        pred_id, into_id, syn_type,
                        weight=edge_data.get("weight", 0.5),
                    )

            await self.circuit.remove_neuron(sid)

        # Append merged content
        if extra_content:
            merged_content = target.content + "\n\n---\n\n" + "\n\n---\n\n".join(extra_content)
            updated = Neuron(
                id=target.id,
                content=merged_content,
                type=target.type,
                domain=target.domain,
                source=target.source,
                created_at=target.created_at,
            )
            await self.circuit.update_neuron(updated)
            target = updated

        self._merged.append((source_ids, into_id))
        return target

    def reset(self) -> None:
        """Reset session tracking state."""
        self._added.clear()
        self._linked.clear()
        self._merged.clear()

    async def close(self) -> None:
        """End the session."""
        if self.persist:
            await self.circuit.commit_retrieval_boosts()
        self.reset()

    @property
    def stats(self) -> dict:
        """Session statistics."""
        return {
            "added": len(self._added),
            "linked": len(self._linked),
            "merged": len(self._merged),
            "added_ids": list(self._added),
            "persist": self.persist,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
