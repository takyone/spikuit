"""Tests for QABot — read-only client for exported Brain bundles."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Neuron, Source
from spikuit_core.config import BrainConfig, EmbedderConfig
from spikuit_core.embedder import Embedder
from spikuit_core.export import export_qabot_bundle
from spikuit_core.rag import EmbedderConfigError, QABot


# -- Fixtures --------------------------------------------------------------


class _DeterministicEmbedder(Embedder):
    """Returns a vector seeded by the text. For tests only."""

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        # Simple bag-of-chars hash → deterministic vector
        vec = [0.0] * self._dimension
        for i, ch in enumerate(text):
            vec[i % self._dimension] += (ord(ch) % 17) / 17.0
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


@pytest_asyncio.fixture
async def populated_brain(tmp_path):
    """A Brain with a few neurons, embeddings, sources, and a _meta neuron."""
    embedder = _DeterministicEmbedder(dimension=8)
    c = Circuit(db_path=tmp_path / "brain.db", embedder=embedder)
    await c.connect()

    n1 = Neuron.create("---\ntype: concept\ndomain: math\n---\n# Monad\n\n型の文脈化を表す抽象")
    n2 = Neuron.create("---\ntype: concept\ndomain: math\n---\n# Functor\n\n圏の間の写像")
    n3 = Neuron.create("---\ntype: vocab\ndomain: french\n---\n# bonjour\n\n挨拶")
    n_meta = Neuron.create(
        "---\ntype: meta\ndomain: _meta\n---\n# math\n\nThis brain covers category theory."
    )
    for n in (n1, n2, n3, n_meta):
        await c.add_neuron(n)

    src = Source(
        url="https://example.com/monad",
        title="Monad reference",
        author="test",
    )
    src = await c.add_source(src)
    await c.attach_source(n1.id, src.id)

    yield c, tmp_path
    await c.close()


@pytest.fixture
def bundle_with_embedder(tmp_path):
    return BrainConfig(
        name="test",
        root=tmp_path,
        embedder=EmbedderConfig(
            provider="openai-compat",
            base_url="http://localhost:1234/v1",
            model="text-embedding-nomic-embed-text-v1.5",
            dimension=8,
            prefix_style="nomic",
        ),
    )


@pytest.fixture
def bundle_no_embedder(tmp_path):
    return BrainConfig(
        name="test",
        root=tmp_path,
        embedder=EmbedderConfig(provider="none"),
    )


@pytest_asyncio.fixture
async def exported_bundle(populated_brain, bundle_with_embedder, tmp_path):
    circuit, _ = populated_brain
    output = tmp_path / "bundle.db"
    await export_qabot_bundle(circuit, bundle_with_embedder, output)
    return output


@pytest_asyncio.fixture
async def keyword_only_bundle(populated_brain, bundle_no_embedder, tmp_path):
    circuit, _ = populated_brain
    output = tmp_path / "kw.db"
    await export_qabot_bundle(circuit, bundle_no_embedder, output)
    return output


# -- Module surface --------------------------------------------------------


def test_qabot_importable_from_top_level():
    from spikuit_core import QABot as TopQABot  # noqa: F401
    from spikuit_core.rag import QABot as RagQABot  # noqa: F401

    assert TopQABot is RagQABot


def test_rag_module_does_not_import_circuit():
    """rag/qabot.py must not pull in heavy engine modules at import time."""
    import importlib
    import sys

    # Force a fresh import path
    for mod in list(sys.modules):
        if mod.startswith("spikuit_core.rag"):
            del sys.modules[mod]

    # Snapshot which modules were already loaded
    before = set(sys.modules)
    importlib.import_module("spikuit_core.rag.qabot")
    new_mods = set(sys.modules) - before

    forbidden = {
        "spikuit_core.circuit",
        "spikuit_core.propagation",
        "spikuit_core.db",
    }
    assert not (forbidden & new_mods), (
        f"rag.qabot pulled forbidden modules: {forbidden & new_mods}"
    )


# -- Load + embedder config resolution -------------------------------------


@pytest.mark.asyncio
async def test_load_reads_embedder_config(exported_bundle, monkeypatch):
    monkeypatch.setenv("SPIKUIT_EMBEDDER_BASE_URL", "http://override:9999/v1")
    monkeypatch.setenv("SPIKUIT_EMBEDDER_API_KEY", "test-key")

    brain = QABot.load(exported_bundle)
    assert brain.embedder_spec.provider == "openai-compat"
    assert brain.embedder_spec.dimension == 8
    assert brain.embedder_spec.prefix_style == "nomic"


@pytest.mark.asyncio
async def test_load_resolution_env_wins(exported_bundle, monkeypatch):
    monkeypatch.setenv("SPIKUIT_EMBEDDER_BASE_URL", "http://from-env/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    brain = QABot.load(exported_bundle, base_url="http://from-arg/v1")
    assert brain.runtime_base_url == "http://from-env/v1"


@pytest.mark.asyncio
async def test_load_resolution_arg_used_when_env_missing(exported_bundle, monkeypatch):
    monkeypatch.delenv("SPIKUIT_EMBEDDER_BASE_URL", raising=False)

    brain = QABot.load(exported_bundle, base_url="http://from-arg/v1")
    assert brain.runtime_base_url == "http://from-arg/v1"


@pytest.mark.asyncio
async def test_load_resolution_bundle_hint_fallback(exported_bundle, monkeypatch):
    monkeypatch.delenv("SPIKUIT_EMBEDDER_BASE_URL", raising=False)

    brain = QABot.load(exported_bundle)
    assert brain.runtime_base_url == "http://localhost:1234/v1"  # bundle hint


@pytest.mark.asyncio
async def test_load_keyword_only_bundle_no_embedder_needed(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    assert brain.embedder_spec.provider == "none"
    assert brain.runtime_base_url is None  # no embedder, no resolution needed


# -- Retrieve --------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_keyword_only(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    results = await brain.retrieve("Monad", limit=5)
    assert len(results) >= 1
    assert any("Monad" in r.content for r in results)


@pytest.mark.asyncio
async def test_retrieve_filters_by_domain(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    results = await brain.retrieve("挨拶", limit=5, domain="french")
    assert all(r.domain == "french" for r in results)
    assert any("bonjour" in r.content for r in results)


@pytest.mark.asyncio
async def test_retrieve_returns_neuron_id_and_content(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    results = await brain.retrieve("Functor", limit=5)
    assert len(results) >= 1
    r = results[0]
    assert r.neuron_id
    assert r.content
    assert r.score >= 0.0


@pytest.mark.asyncio
async def test_retrieve_with_embedder_uses_semantic(exported_bundle, monkeypatch):
    monkeypatch.delenv("SPIKUIT_EMBEDDER_BASE_URL", raising=False)
    brain = QABot.load(exported_bundle)
    # Inject a deterministic embedder so we don't need a real LM Studio
    brain._embedder = _DeterministicEmbedder(dimension=8)

    results = await brain.retrieve("Monad", limit=5)
    assert len(results) >= 1


# -- system_prompt ---------------------------------------------------------


@pytest.mark.asyncio
async def test_system_prompt_concatenates_meta_neurons(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    prompt = brain.system_prompt()
    assert "category theory" in prompt


@pytest.mark.asyncio
async def test_system_prompt_empty_when_no_meta(populated_brain, bundle_no_embedder, tmp_path):
    """Empty _meta should yield empty prompt without crashing."""
    circuit, _ = populated_brain
    # Build a fresh brain with no _meta neuron
    other = Circuit(db_path=tmp_path / "no_meta.db")
    await other.connect()
    try:
        await other.add_neuron(
            Neuron.create("---\ntype: concept\ndomain: math\n---\n# x\n\nbody")
        )
        out = tmp_path / "no_meta_bundle.db"
        cfg = BrainConfig(
            name="t",
            root=tmp_path,
            embedder=EmbedderConfig(provider="none"),
        )
        await export_qabot_bundle(other, cfg, out)
    finally:
        await other.close()

    brain = QABot.load(out)
    assert brain.system_prompt() == ""


# -- Inspection helpers ----------------------------------------------------


@pytest.mark.asyncio
async def test_domains_lists_distinct(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    domains = brain.domains()
    assert "math" in domains
    assert "french" in domains


@pytest.mark.asyncio
async def test_stats_returns_counts(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    s = brain.stats()
    assert s["neurons"] >= 4
    assert s["sources"] >= 1


@pytest.mark.asyncio
async def test_neuron_by_id(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    results = await brain.retrieve("Monad", limit=1)
    nid = results[0].neuron_id
    fetched = brain.neuron(nid)
    assert fetched is not None
    assert fetched.neuron_id == nid


@pytest.mark.asyncio
async def test_sources_for_neuron(keyword_only_bundle):
    brain = QABot.load(keyword_only_bundle)
    results = await brain.retrieve("Monad", limit=5)
    monad = next(r for r in results if "Monad" in r.content)
    srcs = brain.sources(monad.neuron_id)
    assert len(srcs) >= 1
    assert srcs[0]["url"] == "https://example.com/monad"


# -- Error paths -----------------------------------------------------------


def test_load_nonexistent_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        QABot.load(tmp_path / "missing.db")


@pytest.mark.asyncio
async def test_retrieve_without_resolved_embedder_falls_back_to_keyword(
    exported_bundle, monkeypatch
):
    """If env vars are unset and only bundle hint is available, retrieve still
    works in keyword-only mode if the embedder isn't reachable. We don't
    actually call the embedder here — just verify keyword path is reachable."""
    monkeypatch.delenv("SPIKUIT_EMBEDDER_BASE_URL", raising=False)
    brain = QABot.load(exported_bundle)
    # Force embedder to None to simulate "not resolvable"
    brain._embedder = None
    results = await brain.retrieve("Monad", limit=5)
    assert len(results) >= 1
