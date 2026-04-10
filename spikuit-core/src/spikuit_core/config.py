"""Config — project-local Brain configuration.

Manages .spikuit/ directory discovery and config.toml parsing.
Walks up from CWD to find .spikuit/ (like .git/).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SPIKUIT_DIR = ".spikuit"
CONFIG_FILE = "config.toml"
DB_FILE = "circuit.db"
CACHE_DIR = "cache"

# Default config template
DEFAULT_CONFIG = """\
[brain]
name = "{name}"

[embedder]
# provider: "openai-compat" | "ollama" | "none"
# openai-compat works with LM Studio, Ollama /v1, vLLM, OpenAI, etc.
provider = "none"

# Uncomment and configure for local embeddings (LM Studio):
# provider = "openai-compat"
# base_url = "http://localhost:1234/v1"
# model = "text-embedding-nomic-embed-text-v1.5"
# dimension = 768

# Uncomment for Ollama native API:
# provider = "ollama"
# base_url = "http://localhost:11434"
# model = "nomic-embed-text"
# dimension = 768
"""


@dataclass
class EmbedderConfig:
    """Embedder configuration parsed from config.toml."""

    provider: str = "none"
    base_url: str = ""
    model: str = ""
    dimension: int = 768
    api_key: str = "not-needed"
    timeout: float = 30.0


@dataclass
class BrainConfig:
    """Full Brain configuration."""

    name: str = "default"
    root: Path = field(default_factory=lambda: Path.cwd())
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)

    @property
    def spikuit_dir(self) -> Path:
        return self.root / SPIKUIT_DIR

    @property
    def db_path(self) -> Path:
        return self.spikuit_dir / DB_FILE

    @property
    def config_path(self) -> Path:
        return self.spikuit_dir / CONFIG_FILE

    @property
    def cache_path(self) -> Path:
        return self.spikuit_dir / CACHE_DIR


def find_spikuit_root(start: Path | None = None) -> Path | None:
    """Walk up from start to find a directory containing .spikuit/.

    Returns the directory containing .spikuit/, or None if not found.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / SPIKUIT_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_config(root: Path | None = None) -> BrainConfig:
    """Load BrainConfig from .spikuit/config.toml.

    If root is None, walks up from CWD to find .spikuit/.
    Falls back to ~/.spikuit/ if no project-local config found.
    """
    if root is None:
        found = find_spikuit_root()
        if found is not None:
            root = found
        else:
            # Fallback to global
            root = Path.home()

    config_path = root / SPIKUIT_DIR / CONFIG_FILE
    config = BrainConfig(root=root)

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        _apply_config(config, data)

    return config


def init_brain(
    path: Path | None = None,
    *,
    name: str | None = None,
    embedder_provider: str = "none",
    embedder_base_url: str = "",
    embedder_model: str = "",
    embedder_dimension: int = 768,
) -> BrainConfig:
    """Initialize a new .spikuit/ directory with config.toml.

    Returns the BrainConfig for the initialized brain.
    """
    root = (path or Path.cwd()).resolve()
    spikuit_dir = root / SPIKUIT_DIR

    if spikuit_dir.exists():
        raise FileExistsError(f".spikuit/ already exists at {root}")

    brain_name = name or root.name

    # Create directory structure
    spikuit_dir.mkdir(parents=True)
    (spikuit_dir / CACHE_DIR).mkdir()

    # Write config
    config_content = DEFAULT_CONFIG.format(name=brain_name)

    # Override defaults if embedder settings provided
    if embedder_provider != "none":
        config_content = _build_config(
            brain_name, embedder_provider, embedder_base_url,
            embedder_model, embedder_dimension,
        )

    (spikuit_dir / CONFIG_FILE).write_text(config_content)

    return load_config(root)


def _apply_config(config: BrainConfig, data: dict[str, Any]) -> None:
    """Apply parsed TOML data to a BrainConfig."""
    brain = data.get("brain", {})
    if "name" in brain:
        config.name = brain["name"]

    emb = data.get("embedder", {})
    if emb:
        config.embedder = EmbedderConfig(
            provider=emb.get("provider", "none"),
            base_url=emb.get("base_url", ""),
            model=emb.get("model", ""),
            dimension=emb.get("dimension", 768),
            api_key=emb.get("api_key", "not-needed"),
            timeout=emb.get("timeout", 30.0),
        )


def _build_config(
    name: str,
    provider: str,
    base_url: str,
    model: str,
    dimension: int,
) -> str:
    """Build a config.toml string with active embedder settings."""
    lines = [
        f'[brain]',
        f'name = "{name}"',
        f'',
        f'[embedder]',
        f'provider = "{provider}"',
    ]
    if base_url:
        lines.append(f'base_url = "{base_url}"')
    if model:
        lines.append(f'model = "{model}"')
    lines.append(f'dimension = {dimension}')
    return "\n".join(lines) + "\n"
