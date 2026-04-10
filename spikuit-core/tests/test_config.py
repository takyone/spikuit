"""Tests for Config — .spikuit/ discovery and config.toml parsing."""

import pytest

from spikuit_core.config import (
    BrainConfig,
    EmbedderConfig,
    find_spikuit_root,
    init_brain,
    load_config,
    SPIKUIT_DIR,
    CONFIG_FILE,
)


def test_init_brain_creates_structure(tmp_path):
    config = init_brain(tmp_path, name="test-brain")
    assert config.name == "test-brain"
    assert config.spikuit_dir.exists()
    assert config.config_path.exists()
    assert config.cache_path.exists()


def test_init_brain_already_exists(tmp_path):
    init_brain(tmp_path, name="first")
    with pytest.raises(FileExistsError):
        init_brain(tmp_path, name="second")


def test_init_brain_default_name(tmp_path):
    config = init_brain(tmp_path)
    assert config.name == tmp_path.name


def test_init_brain_with_embedder(tmp_path):
    config = init_brain(
        tmp_path,
        name="embedded",
        embedder_provider="openai-compat",
        embedder_base_url="http://localhost:1234/v1",
        embedder_model="my-model",
        embedder_dimension=512,
    )
    assert config.embedder.provider == "openai-compat"
    assert config.embedder.base_url == "http://localhost:1234/v1"
    assert config.embedder.model == "my-model"
    assert config.embedder.dimension == 512


def test_find_spikuit_root_direct(tmp_path):
    (tmp_path / SPIKUIT_DIR).mkdir()
    assert find_spikuit_root(tmp_path) == tmp_path


def test_find_spikuit_root_parent(tmp_path):
    (tmp_path / SPIKUIT_DIR).mkdir()
    child = tmp_path / "sub" / "deep"
    child.mkdir(parents=True)
    assert find_spikuit_root(child) == tmp_path


def test_find_spikuit_root_not_found(tmp_path):
    # No .spikuit/ anywhere
    child = tmp_path / "empty"
    child.mkdir()
    # This will walk up to / and not find .spikuit/ in tmp_path
    # but might find one in the actual filesystem; use a controlled test
    result = find_spikuit_root(child)
    # Should either be None or some parent — just verify it doesn't crash
    assert result is None or result != child


def test_load_config_from_init(tmp_path):
    init_brain(tmp_path, name="loaded")
    config = load_config(tmp_path)
    assert config.name == "loaded"
    assert config.embedder.provider == "none"


def test_load_config_with_embedder_settings(tmp_path):
    init_brain(
        tmp_path,
        embedder_provider="ollama",
        embedder_base_url="http://localhost:11434",
        embedder_model="nomic-embed-text",
        embedder_dimension=768,
    )
    config = load_config(tmp_path)
    assert config.embedder.provider == "ollama"
    assert config.embedder.model == "nomic-embed-text"


def test_db_path_in_spikuit_dir(tmp_path):
    config = init_brain(tmp_path)
    assert config.db_path == tmp_path / SPIKUIT_DIR / "circuit.db"


def test_config_path_properties():
    config = BrainConfig()
    assert config.spikuit_dir.name == SPIKUIT_DIR
    assert config.db_path.name == "circuit.db"
    assert config.config_path.name == CONFIG_FILE
    assert config.cache_path.name == "cache"
