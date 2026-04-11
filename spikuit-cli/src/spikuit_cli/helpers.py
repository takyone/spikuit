"""Shared helpers for spkt CLI commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from spikuit_core import Circuit, Grade, Neuron
from spikuit_core.config import BrainConfig, load_config
from spikuit_core.embedder import create_embedder


def _load_brain_config(brain: Path | None = None) -> BrainConfig:
    """Load config from .spikuit/ or use explicit brain root."""
    return load_config(brain)


def _get_circuit(brain: Path | None = None) -> Circuit:
    """Create a Circuit from brain config."""
    config = load_config(brain)
    embedder = create_embedder(
        config.embedder.provider,
        base_url=config.embedder.base_url,
        model=config.embedder.model,
        dimension=config.embedder.dimension,
        api_key=config.embedder.api_key,
        timeout=config.embedder.timeout,
        prefix_style=config.embedder.prefix_style,
    )
    return Circuit(db_path=config.db_path, embedder=embedder)


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _out(data: object, *, use_json: bool) -> None:
    """Output data as JSON or human-readable text."""
    if use_json:
        typer.echo(json.dumps(data, ensure_ascii=False, default=str))
    elif isinstance(data, str):
        typer.echo(data)
    elif isinstance(data, list):
        for item in data:
            typer.echo(item)
    elif isinstance(data, dict):
        for k, v in data.items():
            typer.echo(f"{k}: {v}")


def _extract_title(content: str) -> str:
    """Extract first heading or first line as title."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line and not line.startswith("---"):
            return line[:60]
    return "(untitled)"


def _neuron_dict(n: Neuron, circuit: Circuit) -> dict:
    """Serialize a Neuron + its graph state to a dict."""
    card = circuit.get_card(n.id)
    pressure = circuit.get_pressure(n.id)
    d: dict = {
        "id": n.id,
        "title": _extract_title(n.content),
        "content": n.content,
        "type": n.type,
        "domain": n.domain,
        "pressure": pressure,
    }
    if card:
        d["fsrs"] = {
            "stability": card.stability,
            "difficulty": card.difficulty,
            "state": card.state.name,
            "due": str(card.due),
        }
    return d


_GRADE_MAP = {
    "miss": Grade.MISS,
    "weak": Grade.WEAK,
    "fire": Grade.FIRE,
    "strong": Grade.STRONG,
}
