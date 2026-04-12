"""Tests for qabot export bundle — schema and embedder_config round-trip."""

import sqlite3

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Neuron
from spikuit_core.config import BrainConfig, EmbedderConfig
from spikuit_core.export import export_qabot_bundle


@pytest_asyncio.fixture
async def brain(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


@pytest.fixture
def config_with_embedder(tmp_path):
    return BrainConfig(
        name="test",
        root=tmp_path,
        embedder=EmbedderConfig(
            provider="openai-compat",
            base_url="http://localhost:1234/v1",
            model="text-embedding-nomic-embed-text-v1.5",
            dimension=768,
            prefix_style="nomic",
        ),
    )


@pytest.fixture
def config_none_embedder(tmp_path):
    return BrainConfig(
        name="test",
        root=tmp_path,
        embedder=EmbedderConfig(provider="none"),
    )


# -- Schema ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_creates_all_tables(brain, config_with_embedder, tmp_path):
    output = tmp_path / "bundle.db"
    await export_qabot_bundle(brain, config_with_embedder, output)

    assert output.exists()
    conn = sqlite3.connect(str(output))
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {"neuron", "synapse", "source", "neuron_source", "embedder_config"}
        assert expected.issubset(tables)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_embedder_config_round_trip(brain, config_with_embedder, tmp_path):
    output = tmp_path / "bundle.db"
    await export_qabot_bundle(brain, config_with_embedder, output)

    conn = sqlite3.connect(str(output))
    try:
        row = conn.execute(
            "SELECT provider, model, dimension, prefix_style, original_base_url FROM embedder_config"
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "openai-compat",
        "text-embedding-nomic-embed-text-v1.5",
        768,
        "nomic",
        "http://localhost:1234/v1",
    )


@pytest.mark.asyncio
async def test_embedder_config_none_provider(brain, config_none_embedder, tmp_path):
    output = tmp_path / "bundle.db"
    await export_qabot_bundle(brain, config_none_embedder, output)

    conn = sqlite3.connect(str(output))
    try:
        row = conn.execute(
            "SELECT provider, dimension FROM embedder_config"
        ).fetchone()
    finally:
        conn.close()

    assert row[0] == "none"


@pytest.mark.asyncio
async def test_embedder_config_never_stores_api_key(
    brain, tmp_path
):
    config = BrainConfig(
        name="test",
        root=tmp_path,
        embedder=EmbedderConfig(
            provider="openai-compat",
            base_url="https://api.example.com/v1",
            model="m",
            dimension=768,
            api_key="sk-SECRET-DO-NOT-LEAK",
        ),
    )
    output = tmp_path / "bundle.db"
    await export_qabot_bundle(brain, config, output)

    conn = sqlite3.connect(str(output))
    try:
        cols = [
            r[1]
            for r in conn.execute("PRAGMA table_info(embedder_config)").fetchall()
        ]
        # Scan every value in the file for the secret
        all_rows = conn.execute(
            "SELECT * FROM embedder_config"
        ).fetchall()
    finally:
        conn.close()

    assert "api_key" not in cols
    for row in all_rows:
        for val in row:
            assert "SECRET" not in str(val)


# -- Data content ----------------------------------------------------------


@pytest.mark.asyncio
async def test_export_includes_neurons(brain, config_with_embedder, tmp_path):
    n1 = Neuron.create("---\ntype: concept\ndomain: math\n---\n# Monad\n\n型の文脈化")
    n2 = Neuron.create("---\ntype: concept\ndomain: math\n---\n# Functor\n\n圏の写像")
    await brain.add_neuron(n1)
    await brain.add_neuron(n2)

    output = tmp_path / "bundle.db"
    await export_qabot_bundle(brain, config_with_embedder, output)

    conn = sqlite3.connect(str(output))
    try:
        count = conn.execute("SELECT COUNT(*) FROM neuron").fetchone()[0]
    finally:
        conn.close()

    assert count == 2


@pytest.mark.asyncio
async def test_export_is_importable_without_spikuit_cli(
    brain, config_with_embedder, tmp_path
):
    # export_qabot_bundle must live in core, not cli
    import spikuit_core.export as export_mod

    assert hasattr(export_mod, "export_qabot_bundle")
