"""Tests for Session — QABotSession and IngestSession."""

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Neuron, Source, SynapseType
from spikuit_core.embedder import Embedder
from spikuit_core.session import IngestSession, QABotSession, _cosine_sim


# -- FakeEmbedder (same as test_embedder.py) ---------------------------------


class FakeEmbedder(Embedder):
    KEYWORDS = ["math", "category", "functor", "morphism", "language", "verb", "french", "neural"]

    @property
    def dimension(self) -> int:
        return len(self.KEYWORDS)

    async def embed(self, text: str) -> list[float]:
        lower = text.lower()
        return [1.0 if kw in lower else 0.0 for kw in self.KEYWORDS]


# -- Fixtures ----------------------------------------------------------------


@pytest_asyncio.fixture
async def circuit(tmp_path):
    emb = FakeEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    # Populate with test neurons
    await c.add_neuron(Neuron.create(
        "# Functor\n\nA mapping in category theory preserving structure.",
        id="math1",
    ))
    await c.add_neuron(Neuron.create(
        "# Morphism\n\nAn arrow in category theory between objects.",
        id="math2",
    ))
    await c.add_neuron(Neuron.create(
        "# Natural Transformation\n\nA morphism between functors in category math.",
        id="math3",
    ))
    await c.add_neuron(Neuron.create(
        "# French Verbs\n\nConjugation of regular -er verbs in French language.",
        id="lang1",
    ))
    await c.add_neuron(Neuron.create(
        "# French Grammar\n\nBasic French language rules for verb usage.",
        id="lang2",
    ))

    yield c
    await c.close()


@pytest_asyncio.fixture
async def empty_circuit(tmp_path):
    """Circuit with no neurons — for IngestSession tests."""
    emb = FakeEmbedder()
    c = Circuit(db_path=tmp_path / "learn.db", embedder=emb)
    await c.connect()
    yield c
    await c.close()


# -- Cosine similarity helper ------------------------------------------------


def test_cosine_sim_identical():
    assert _cosine_sim([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_sim_orthogonal():
    assert _cosine_sim([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)


def test_cosine_sim_zero_vector():
    assert _cosine_sim([0, 0, 0], [1, 0, 0]) == pytest.approx(0.0)


# -- QABotSession.ask -------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_returns_relevant_results(circuit):
    session = QABotSession(circuit, persist=False)
    results = await session.ask("category functor")
    ids = [r.neuron_id for r in results]
    # Should find math neurons (they contain "category" and/or "functor")
    assert any("math" in nid for nid in ids)
    assert session.turns == 1


@pytest.mark.asyncio
async def test_ask_excludes_seen_by_default(circuit):
    session = QABotSession(circuit, persist=False)
    r1 = await session.ask("category", limit=2)
    ids1 = {r.neuron_id for r in r1}

    r2 = await session.ask("category math", limit=5)
    ids2 = {r.neuron_id for r in r2}

    # Second ask should not return neurons from first ask
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_ask_no_exclude_when_disabled(circuit):
    session = QABotSession(circuit, persist=False, exclude_seen=False)
    r1 = await session.ask("category", limit=2)
    ids1 = {r.neuron_id for r in r1}

    r2 = await session.ask("category math", limit=5)
    ids2 = {r.neuron_id for r in r2}

    # Without exclude_seen, overlap is allowed
    # (may or may not overlap depending on scoring, but at least no filtering)
    assert session.turns == 2


@pytest.mark.asyncio
async def test_ask_includes_context_ids(circuit):
    """Results include ensemble neighbor IDs."""
    from spikuit_core import SynapseType
    await circuit.add_synapse("math1", "math2", SynapseType.REQUIRES)

    session = QABotSession(circuit, persist=False)
    results = await session.ask("functor")
    functor_result = next((r for r in results if r.neuron_id == "math1"), None)
    if functor_result:
        # math2 should be in context since it's a neighbor
        assert "math2" in functor_result.context_ids


# -- Negative feedback -------------------------------------------------------


@pytest.mark.asyncio
async def test_followup_applies_negative_feedback(circuit):
    session = QABotSession(circuit, persist=False, learning_rate=0.5)

    # First ask
    await session.ask("category functor")

    # Record boosts before follow-up
    boosts_before = {nid: circuit.get_retrieval_boost(nid) for nid in ["math1", "math2", "math3"]}

    # Similar follow-up → negative feedback on prior results
    await session.ask("category morphism")

    # Prior results should have been penalized
    any_penalized = False
    for nid in ["math1", "math2", "math3"]:
        if circuit.get_retrieval_boost(nid) < boosts_before.get(nid, 0.0):
            any_penalized = True
    assert any_penalized


@pytest.mark.asyncio
async def test_accepted_neurons_not_penalized(circuit):
    session = QABotSession(circuit, persist=False, learning_rate=0.5)

    r1 = await session.ask("category functor")
    accepted_id = r1[0].neuron_id
    await session.accept([accepted_id])

    boost_after_accept = circuit.get_retrieval_boost(accepted_id)

    # Follow-up similar query
    await session.ask("category math")

    # Accepted neuron should NOT be penalized
    assert circuit.get_retrieval_boost(accepted_id) >= boost_after_accept


# -- Accept ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_boosts_neurons(circuit):
    session = QABotSession(circuit, persist=False)
    await session.ask("functor category")

    boost_before = circuit.get_retrieval_boost("math1")
    await session.accept(["math1"])
    boost_after = circuit.get_retrieval_boost("math1")

    assert boost_after > boost_before


@pytest.mark.asyncio
async def test_accept_diminishing_returns(circuit):
    session = QABotSession(circuit, persist=False, learning_rate=0.5)
    await session.ask("functor")

    await session.accept(["math1"])
    gain1 = circuit.get_retrieval_boost("math1")

    await session.accept(["math1"])
    gain2 = circuit.get_retrieval_boost("math1") - gain1

    # Second accept should give less boost (diminishing returns)
    assert gain2 < gain1


# -- Reset -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_session_state(circuit):
    session = QABotSession(circuit, persist=False)
    await session.ask("category")
    assert session.turns == 1
    assert len(session._all_returned) > 0

    session.reset()

    assert session.turns == 0
    assert len(session._all_returned) == 0
    assert len(session._accepted) == 0


@pytest.mark.asyncio
async def test_reset_allows_same_neurons_again(circuit):
    session = QABotSession(circuit, persist=False)
    r1 = await session.ask("category", limit=2)
    ids1 = {r.neuron_id for r in r1}

    session.reset()

    r2 = await session.ask("category", limit=2)
    ids2 = {r.neuron_id for r in r2}

    # After reset, same neurons can be returned
    assert ids1 == ids2


# -- Persistence -------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_session_commits_boosts(circuit):
    session = QABotSession(circuit, persist=True, learning_rate=0.5)
    await session.ask("functor")
    await session.accept(["math1"])
    await session.close()

    # Boost should be persisted in DB
    db_boost = await circuit._db.get_retrieval_boost("math1")
    assert db_boost > 0.0


@pytest.mark.asyncio
async def test_ephemeral_session_discards_boosts(circuit):
    session = QABotSession(circuit, persist=False, learning_rate=0.5)
    await session.ask("functor")
    await session.accept(["math1"])
    await session.close()

    # In-memory boost is set but NOT committed to DB
    db_boost = await circuit._db.get_retrieval_boost("math1")
    assert db_boost == 0.0


@pytest.mark.asyncio
async def test_persistent_boosts_survive_reconnect(tmp_path):
    """Boosts committed by a persistent session survive circuit reconnect."""
    emb = FakeEmbedder()

    # Session 1: build and accept
    c1 = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c1.connect()
    await c1.add_neuron(Neuron.create("# Functor in category math", id="math1"))
    session = QABotSession(c1, persist=True, learning_rate=0.5)
    await session.ask("functor")
    await session.accept(["math1"])
    await session.close()
    await c1.close()

    # Session 2: reconnect and verify
    c2 = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c2.connect()
    assert c2.get_retrieval_boost("math1") > 0.0
    await c2.close()


# -- Stats -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_stats(circuit):
    session = QABotSession(circuit, persist=False)
    await session.ask("category")
    await session.accept(["math1"])

    stats = session.stats
    assert stats["turns"] == 1
    assert stats["accepted"] == 1
    assert stats["persist"] is False
    assert stats["total_returned"] > 0


# ===========================================================================
# IngestSession
# ===========================================================================


# -- Ingest ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_creates_neuron(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    neuron, related = await session.ingest(
        "# Functor\n\nA mapping between categories.",
        type="concept",
        domain="math",
    )
    assert neuron.id.startswith("n-")
    assert neuron.type == "concept"
    assert neuron.domain == "math"

    # Should be in circuit
    got = await empty_circuit.get_neuron(neuron.id)
    assert got is not None
    assert got.content == neuron.content


@pytest.mark.asyncio
async def test_ingest_with_custom_id(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    neuron, _ = await session.ingest("# Test", id="custom-id")
    assert neuron.id == "custom-id"


@pytest.mark.asyncio
async def test_ingest_returns_related_neurons(circuit):
    session = IngestSession(circuit, persist=False)
    neuron, related = await session.ingest(
        "# Adjunction\n\nA functor pair in category theory.",
    )
    # Should find existing math neurons as related
    related_ids = [n.id for n in related]
    assert any("math" in nid for nid in related_ids)
    # Should not include the neuron itself
    assert neuron.id not in related_ids


@pytest.mark.asyncio
async def test_ingest_no_auto_relate(empty_circuit):
    session = IngestSession(empty_circuit, persist=False, auto_relate=False)
    _, related = await session.ingest("# Test concept")
    assert related == []


@pytest.mark.asyncio
async def test_ingest_tracks_added(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# First")
    n2, _ = await session.ingest("# Second")
    assert session.stats["added"] == 2
    assert n1.id in session.stats["added_ids"]
    assert n2.id in session.stats["added_ids"]


# -- Relate ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relate_creates_synapse(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# Functor\n\nCategory math concept")
    n2, _ = await session.ingest("# Morphism\n\nCategory math arrow")

    synapses = await session.relate(n1.id, n2.id, SynapseType.REQUIRES)
    assert len(synapses) == 1
    assert synapses[0].pre == n1.id
    assert synapses[0].post == n2.id


@pytest.mark.asyncio
async def test_relate_bidirectional(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# A")
    n2, _ = await session.ingest("# B")

    synapses = await session.relate(n1.id, n2.id, SynapseType.RELATES_TO)
    # Bidirectional creates two synapses
    assert len(synapses) == 2


@pytest.mark.asyncio
async def test_relate_strengthens_existing(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# A")
    n2, _ = await session.ingest("# B")

    await session.relate(n1.id, n2.id, SynapseType.REQUIRES, weight=0.5)

    # Relate again — should strengthen, not duplicate
    result = await session.relate(n1.id, n2.id, SynapseType.REQUIRES)
    assert len(result) == 1
    assert result[0].weight == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_relate_strengthen_caps_at_ceiling(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# A")
    n2, _ = await session.ingest("# B")

    await session.relate(n1.id, n2.id, SynapseType.REQUIRES, weight=0.95)
    result = await session.relate(n1.id, n2.id, SynapseType.REQUIRES)
    assert result[0].weight <= empty_circuit.plasticity.weight_ceiling


@pytest.mark.asyncio
async def test_relate_tracks_linked(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# A")
    n2, _ = await session.ingest("# B")
    await session.relate(n1.id, n2.id)
    assert session.stats["linked"] == 1


# -- Search ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_finds_neurons(circuit):
    session = IngestSession(circuit, persist=False)
    results = await session.search("category functor")
    assert len(results) > 0
    ids = [n.id for n in results]
    assert any("math" in nid for nid in ids)


@pytest.mark.asyncio
async def test_search_empty_query(circuit):
    session = IngestSession(circuit, persist=False)
    results = await session.search("")
    assert results == []


# -- Merge -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_combines_content(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# Main concept", id="main")
    n2, _ = await session.ingest("# Duplicate with extra info", id="dup")

    result = await session.merge(["dup"], "main")
    assert "Main concept" in result.content
    assert "Duplicate with extra info" in result.content
    assert "---" in result.content

    # Source should be removed
    assert await empty_circuit.get_neuron("dup") is None


@pytest.mark.asyncio
async def test_merge_transfers_synapses(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# Target", id="target")
    n2, _ = await session.ingest("# Source", id="source")
    n3, _ = await session.ingest("# Related", id="related")

    # source -> related
    await session.relate("source", "related", SynapseType.REQUIRES)

    await session.merge(["source"], "target")

    # target should now have the synapse to related
    assert empty_circuit._graph.has_edge("target", "related")
    # source should be gone
    assert "source" not in empty_circuit._graph


@pytest.mark.asyncio
async def test_merge_transfers_incoming_synapses(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# Target", id="target")
    n2, _ = await session.ingest("# Source", id="source")
    n3, _ = await session.ingest("# Prereq", id="prereq")

    # prereq -> source
    await session.relate("prereq", "source", SynapseType.REQUIRES)

    await session.merge(["source"], "target")

    # prereq -> target should exist
    assert empty_circuit._graph.has_edge("prereq", "target")


@pytest.mark.asyncio
async def test_merge_nonexistent_target_raises(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    with pytest.raises(ValueError, match="not found"):
        await session.merge(["whatever"], "nonexistent")


@pytest.mark.asyncio
async def test_merge_skips_self(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    n1, _ = await session.ingest("# Self", id="self")

    # Merge self into self should not crash or duplicate content
    result = await session.merge(["self"], "self")
    assert result.content == "# Self"


@pytest.mark.asyncio
async def test_merge_tracks_stats(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    await session.ingest("# A", id="a")
    await session.ingest("# B", id="b")
    await session.merge(["b"], "a")
    assert session.stats["merged"] == 1


# -- Reset / Close -----------------------------------------------------------


@pytest.mark.asyncio
async def test_learn_session_reset(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    await session.ingest("# A")
    assert session.stats["added"] == 1

    session.reset()
    assert session.stats["added"] == 0
    assert session.stats["linked"] == 0
    assert session.stats["merged"] == 0


@pytest.mark.asyncio
async def test_learn_session_close(empty_circuit):
    session = IngestSession(empty_circuit, persist=False)
    await session.ingest("# A")
    await session.close()
    assert session.stats["added"] == 0


# -- Source ingestion --------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_with_source_meta(empty_circuit):
    """ingest() with source_meta creates and attaches Source."""
    session = IngestSession(empty_circuit, persist=False)
    src = Source(url="https://example.com/paper.pdf", title="A Paper")
    neuron, _ = await session.ingest(
        "# Key Finding\n\nSomething important.",
        source_meta=src,
    )

    sources = await empty_circuit.get_sources_for_neuron(neuron.id)
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/paper.pdf"


@pytest.mark.asyncio
async def test_ingest_source_dedup_by_url(empty_circuit):
    """Multiple ingests with same source URL should reuse the Source."""
    session = IngestSession(empty_circuit, persist=False)
    src1 = Source(url="https://example.com/paper.pdf", title="Paper")
    src2 = Source(url="https://example.com/paper.pdf", title="Paper v2")

    n1, _ = await session.ingest("# Finding 1", source_meta=src1)
    n2, _ = await session.ingest("# Finding 2", source_meta=src2)

    s1 = await empty_circuit.get_sources_for_neuron(n1.id)
    s2 = await empty_circuit.get_sources_for_neuron(n2.id)
    # Both should point to the same source (first one created)
    assert s1[0].id == s2[0].id


@pytest.mark.asyncio
async def test_ingest_without_source_meta(empty_circuit):
    """ingest() without source_meta should not create Source."""
    session = IngestSession(empty_circuit, persist=False)
    neuron, _ = await session.ingest("# No Source")
    sources = await empty_circuit.get_sources_for_neuron(neuron.id)
    assert len(sources) == 0


# -- QABot citation ----------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_includes_sources_in_results(circuit):
    """QABotSession.ask() results include attached sources."""
    # Attach a source to math1
    src = Source(url="https://cattheory.org", title="CT Book")
    await circuit.add_source(src)
    await circuit.attach_source("math1", src.id)

    session = QABotSession(circuit, persist=False)
    results = await session.ask("functor category")

    functor_result = next((r for r in results if r.neuron_id == "math1"), None)
    assert functor_result is not None
    assert len(functor_result.sources) == 1
    assert functor_result.sources[0].url == "https://cattheory.org"


@pytest.mark.asyncio
async def test_ask_no_sources_when_none_attached(circuit):
    """Results with no attached sources have empty sources list."""
    session = QABotSession(circuit, persist=False)
    results = await session.ask("functor")

    for r in results:
        assert isinstance(r.sources, list)
