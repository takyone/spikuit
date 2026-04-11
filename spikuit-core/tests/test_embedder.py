"""Tests for Embedder — embedding providers and sqlite-vec integration."""

import math

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Neuron, NullEmbedder
from spikuit_core.embedder import Embedder, EmbeddingType, OpenAICompatEmbedder, OllamaEmbedder, vec_to_blob, blob_to_vec


# ---------------------------------------------------------------------------
# A deterministic fake embedder for testing (no external API)
# ---------------------------------------------------------------------------


class FakeEmbedder(Embedder):
    """Produces deterministic embeddings based on keyword presence.

    Each dimension corresponds to a keyword. If the keyword is present
    in the text, that dimension is 1.0, otherwise 0.0. This gives us
    controllable cosine similarity for testing.
    """

    KEYWORDS = ["math", "category", "functor", "morphism", "language", "verb", "french", "neural"]

    @property
    def dimension(self) -> int:
        return len(self.KEYWORDS)

    async def embed(self, text: str) -> list[float]:
        lower = text.lower()
        return [1.0 if kw in lower else 0.0 for kw in self.KEYWORDS]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_vec_roundtrip():
    """vec_to_blob / blob_to_vec roundtrip preserves values."""
    vec = [1.0, 2.5, -0.3, 0.0]
    blob = vec_to_blob(vec)
    restored = blob_to_vec(blob)
    assert len(restored) == 4
    for a, b in zip(vec, restored):
        assert abs(a - b) < 1e-6


def test_vec_to_blob_size():
    """Each float32 is 4 bytes."""
    vec = [0.0] * 768
    blob = vec_to_blob(vec)
    assert len(blob) == 768 * 4


# ---------------------------------------------------------------------------
# NullEmbedder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_embedder_returns_zeros():
    emb = NullEmbedder(dimension=4)
    vec = await emb.embed("anything")
    assert vec == [0.0, 0.0, 0.0, 0.0]
    assert emb.dimension == 4


@pytest.mark.asyncio
async def test_null_embedder_batch():
    emb = NullEmbedder(dimension=3)
    vecs = await emb.embed_batch(["a", "b"])
    assert len(vecs) == 2
    assert all(v == [0.0, 0.0, 0.0] for v in vecs)


# ---------------------------------------------------------------------------
# FakeEmbedder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_embedder_keyword_detection():
    emb = FakeEmbedder()
    vec = await emb.embed("A functor in category theory")
    # "functor" is index 2, "category" is index 1
    assert vec[1] == 1.0  # category
    assert vec[2] == 1.0  # functor
    assert vec[4] == 0.0  # language (not present)


# ---------------------------------------------------------------------------
# Circuit + Embedder integration
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def circuit_with_embedder(tmp_path):
    emb = FakeEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()
    yield c
    await c.close()


@pytest_asyncio.fixture
async def circuit_no_embedder(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_add_neuron_auto_embeds(circuit_with_embedder):
    """Adding a neuron with an embedder auto-creates an embedding."""
    circuit = circuit_with_embedder
    n = Neuron.create("# Functor\n\nA morphism in category theory.", id="n1")
    await circuit.add_neuron(n)

    # Check embedding exists in DB
    results = await circuit._db.knn_search(
        vec_to_blob(await circuit._embedder.embed("category functor")),
        limit=5,
    )
    assert any(nid == "n1" for nid, _ in results)


@pytest.mark.asyncio
async def test_add_neuron_without_embedder_no_error(circuit_no_embedder):
    """Adding a neuron without an embedder works fine (no embedding created)."""
    circuit = circuit_no_embedder
    n = Neuron.create("# Test", id="n1")
    await circuit.add_neuron(n)
    got = await circuit.get_neuron("n1")
    assert got is not None


@pytest.mark.asyncio
async def test_semantic_retrieve_finds_related(circuit_with_embedder):
    """Semantic search finds neurons by meaning, not just keywords."""
    circuit = circuit_with_embedder

    await circuit.add_neuron(Neuron.create(
        "# Functor\n\nA mapping between categories preserving structure.",
        id="math1",
    ))
    await circuit.add_neuron(Neuron.create(
        "# Morphism\n\nAn arrow in category theory.",
        id="math2",
    ))
    await circuit.add_neuron(Neuron.create(
        "# French Verbs\n\nConjugation of regular -er verbs in French language.",
        id="lang1",
    ))

    # Search for "category" — should find math neurons, not language
    results = await circuit.retrieve("category")
    result_ids = [n.id for n in results]
    assert "math1" in result_ids
    assert "math2" in result_ids


@pytest.mark.asyncio
async def test_semantic_retrieve_without_keyword_match(circuit_with_embedder):
    """Semantic search can find neurons even without exact keyword match."""
    circuit = circuit_with_embedder

    # "neural" keyword is in FakeEmbedder but won't appear in content directly
    await circuit.add_neuron(Neuron.create(
        "# Neural Networks\n\nDeep learning with neural architectures.",
        id="nn1",
    ))
    await circuit.add_neuron(Neuron.create(
        "# French Grammar\n\nBasic French language rules.",
        id="fr1",
    ))

    # Search "neural" — nn1 has it in content AND embedding
    results = await circuit.retrieve("neural")
    result_ids = [n.id for n in results]
    assert "nn1" in result_ids


@pytest.mark.asyncio
async def test_retrieve_still_works_without_embedder(circuit_no_embedder):
    """Keyword-only retrieve still works when no embedder is set."""
    circuit = circuit_no_embedder
    await circuit.add_neuron(Neuron.create("# Functor\n\nA functor.", id="n1"))
    await circuit.add_neuron(Neuron.create("# Verb\n\nA verb.", id="n2"))

    results = await circuit.retrieve("functor")
    assert len(results) == 1
    assert results[0].id == "n1"


@pytest.mark.asyncio
async def test_embed_all_backfill(tmp_path):
    """embed_all() backfills embeddings for existing neurons."""
    # First create circuit without embedder
    c1 = Circuit(db_path=tmp_path / "test.db")
    await c1.connect()
    await c1.add_neuron(Neuron.create("# Math functor", id="n1"))
    await c1.add_neuron(Neuron.create("# French verb", id="n2"))
    await c1.close()

    # Re-open with embedder and backfill
    emb = FakeEmbedder()
    c2 = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c2.connect()
    count = await c2.embed_all()
    assert count == 2

    # Now semantic search should work
    results = await c2.retrieve("math")
    result_ids = [n.id for n in results]
    assert "n1" in result_ids
    await c2.close()


@pytest.mark.asyncio
async def test_embed_all_skips_existing(circuit_with_embedder):
    """embed_all() doesn't re-embed already embedded neurons."""
    circuit = circuit_with_embedder
    await circuit.add_neuron(Neuron.create("# Test", id="n1"))

    # All are already embedded via add_neuron
    count = await circuit.embed_all()
    assert count == 0


@pytest.mark.asyncio
async def test_update_neuron_re_embeds(circuit_with_embedder):
    """Updating neuron content re-creates the embedding."""
    circuit = circuit_with_embedder
    n = Neuron.create("# Math stuff", id="n1")
    await circuit.add_neuron(n)

    # Update content to something different
    n.content = "# French language verb conjugation"
    await circuit.update_neuron(n)

    # Now searching "french" should find it
    results = await circuit.retrieve("french language")
    result_ids = [n.id for n in results]
    assert "n1" in result_ids


@pytest.mark.asyncio
async def test_remove_neuron_deletes_embedding(circuit_with_embedder):
    """Removing a neuron also removes its embedding."""
    circuit = circuit_with_embedder
    await circuit.add_neuron(Neuron.create("# Functor in math category", id="n1"))

    await circuit.remove_neuron("n1")

    # KNN should return nothing
    emb_vec = await circuit._embedder.embed("functor")
    results = await circuit._db.knn_search(vec_to_blob(emb_vec), limit=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_knn_distance_ordering(circuit_with_embedder):
    """KNN results are ordered by distance (closest first)."""
    circuit = circuit_with_embedder

    # math+category → close to "math category" query
    await circuit.add_neuron(Neuron.create(
        "# Category Theory\n\nMath category foundations.",
        id="close",
    ))
    # language only → far from "math category" query
    await circuit.add_neuron(Neuron.create(
        "# French Language\n\nVerb conjugation.",
        id="far",
    ))

    query_vec = await circuit._embedder.embed("math category")
    results = await circuit._db.knn_search(vec_to_blob(query_vec), limit=5)

    # "close" should be nearer than "far"
    ids = [nid for nid, _ in results]
    assert ids.index("close") < ids.index("far")


# ---------------------------------------------------------------------------
# EmbeddingType + apply_prefix
# ---------------------------------------------------------------------------


def test_base_embedder_apply_prefix_is_noop():
    """Base Embedder.apply_prefix returns text unchanged."""
    emb = NullEmbedder()
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "hello"
    assert emb.apply_prefix("hello", EmbeddingType.QUERY) == "hello"


def test_fake_embedder_apply_prefix_is_noop():
    """FakeEmbedder inherits no-op apply_prefix."""
    emb = FakeEmbedder()
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "hello"


def test_openai_compat_prefix_nomic():
    """OpenAICompatEmbedder with nomic prefix_style prepends correctly."""
    emb = OpenAICompatEmbedder(prefix_style="nomic")
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "search_document: hello"
    assert emb.apply_prefix("hello", EmbeddingType.QUERY) == "search_query: hello"


def test_openai_compat_prefix_cohere():
    """OpenAICompatEmbedder with cohere prefix_style prepends correctly."""
    emb = OpenAICompatEmbedder(prefix_style="cohere")
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "search_document: hello"
    assert emb.apply_prefix("hello", EmbeddingType.QUERY) == "search_query: hello"


def test_openai_compat_prefix_none():
    """OpenAICompatEmbedder with prefix_style='none' returns text unchanged."""
    emb = OpenAICompatEmbedder(prefix_style="none")
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "hello"
    assert emb.apply_prefix("hello", EmbeddingType.QUERY) == "hello"


def test_openai_compat_prefix_default_is_none():
    """Default prefix_style is 'none' (no prefix)."""
    emb = OpenAICompatEmbedder()
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "hello"


def test_ollama_prefix_nomic():
    """OllamaEmbedder with nomic prefix_style prepends correctly."""
    emb = OllamaEmbedder(prefix_style="nomic")
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "search_document: hello"
    assert emb.apply_prefix("hello", EmbeddingType.QUERY) == "search_query: hello"


def test_ollama_prefix_none():
    """OllamaEmbedder with prefix_style='none' returns text unchanged."""
    emb = OllamaEmbedder(prefix_style="none")
    assert emb.apply_prefix("hello", EmbeddingType.DOCUMENT) == "hello"


# ---------------------------------------------------------------------------
# Frontmatter stripping in Circuit embedding pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_neuron_strips_frontmatter_before_embedding(tmp_path):
    """Frontmatter should NOT be included in the embedding vector."""

    captured_texts: list[str] = []

    class CapturingEmbedder(Embedder):
        """Records the text passed to embed() for inspection."""

        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

    emb = CapturingEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    content = "---\ntype: concept\ndomain: math\n---\n# Functor\n\nA mapping between categories."
    n = Neuron.create(content, id="n1")
    await c.add_neuron(n)

    await c.close()

    # The embedded text should be the body, not the frontmatter
    assert len(captured_texts) == 1
    assert "type: concept" not in captured_texts[0]
    assert "domain: math" not in captured_texts[0]
    assert "Functor" in captured_texts[0]


@pytest.mark.asyncio
async def test_embed_all_strips_frontmatter(tmp_path):
    """embed_all() should strip frontmatter before embedding."""

    captured_texts: list[str] = []

    class CapturingEmbedder(Embedder):
        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

    # Create circuit without embedder first
    c1 = Circuit(db_path=tmp_path / "test.db")
    await c1.connect()
    content = "---\nsection: chapter1\n---\n# Monad\n\nA monoid in the category of endofunctors."
    await c1.add_neuron(Neuron.create(content, id="n1"))
    await c1.close()

    # Reopen with capturing embedder and backfill
    emb = CapturingEmbedder()
    c2 = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c2.connect()
    count = await c2.embed_all()
    await c2.close()

    assert count == 1
    assert "section: chapter1" not in captured_texts[0]
    assert "Monad" in captured_texts[0]


@pytest.mark.asyncio
async def test_retrieve_uses_query_prefix(tmp_path):
    """retrieve() should apply EmbeddingType.QUERY prefix to the query."""

    captured_texts: list[str] = []

    class CapturingPrefixEmbedder(Embedder):
        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

        def apply_prefix(self, text: str, embedding_type: EmbeddingType) -> str:
            if embedding_type == EmbeddingType.QUERY:
                return "search_query: " + text
            return "search_document: " + text

    emb = CapturingPrefixEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    await c.add_neuron(Neuron.create("# Test\n\nSome content.", id="n1"))
    captured_texts.clear()  # Clear the add_neuron embed call

    await c.retrieve("my query")
    await c.close()

    # The retrieve call should have used QUERY prefix
    assert any("search_query: my query" == t for t in captured_texts)


@pytest.mark.asyncio
async def test_add_neuron_uses_document_prefix(tmp_path):
    """add_neuron() should apply EmbeddingType.DOCUMENT prefix."""

    captured_texts: list[str] = []

    class CapturingPrefixEmbedder(Embedder):
        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

        def apply_prefix(self, text: str, embedding_type: EmbeddingType) -> str:
            if embedding_type == EmbeddingType.DOCUMENT:
                return "search_document: " + text
            return "search_query: " + text

    emb = CapturingPrefixEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    await c.add_neuron(Neuron.create("# Functor\n\nA mapping.", id="n1"))
    await c.close()

    assert len(captured_texts) == 1
    assert captured_texts[0].startswith("search_document: ")


# ---------------------------------------------------------------------------
# Section context inlining
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_section_inlined_in_embedding(tmp_path):
    """Frontmatter 'section' should be prepended as [Section: X] in embedding text."""

    captured_texts: list[str] = []

    class CapturingEmbedder(Embedder):
        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

    emb = CapturingEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    content = "---\nsection: Chapter 3 - Monads\n---\n# Monad\n\nA monoid in endofunctors."
    await c.add_neuron(Neuron.create(content, id="n1"))
    await c.close()

    assert len(captured_texts) == 1
    assert captured_texts[0].startswith("[Section: Chapter 3 - Monads] ")
    assert "Monad" in captured_texts[0]
    assert "section:" not in captured_texts[0]  # raw frontmatter stripped


@pytest.mark.asyncio
async def test_no_section_no_prefix(tmp_path):
    """Without 'section' in frontmatter, no [Section: ...] prefix is added."""

    captured_texts: list[str] = []

    class CapturingEmbedder(Embedder):
        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

    emb = CapturingEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    content = "---\ntype: concept\n---\n# Functor\n\nA mapping."
    await c.add_neuron(Neuron.create(content, id="n1"))
    await c.close()

    assert len(captured_texts) == 1
    assert not captured_texts[0].startswith("[Section:")
    assert captured_texts[0].startswith("# Functor")


@pytest.mark.asyncio
async def test_no_frontmatter_no_prefix(tmp_path):
    """Content without frontmatter should be embedded as-is."""

    captured_texts: list[str] = []

    class CapturingEmbedder(Embedder):
        @property
        def dimension(self) -> int:
            return 4

        async def embed(self, text: str) -> list[float]:
            captured_texts.append(text)
            return [0.0] * 4

    emb = CapturingEmbedder()
    c = Circuit(db_path=tmp_path / "test.db", embedder=emb)
    await c.connect()

    await c.add_neuron(Neuron.create("# Plain\n\nNo frontmatter here.", id="n1"))
    await c.close()

    assert len(captured_texts) == 1
    assert captured_texts[0] == "# Plain\n\nNo frontmatter here."
