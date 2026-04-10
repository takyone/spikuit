# Spikuit — Development Guide

## Overview

Spikuit (spike + circuit) is a neural knowledge graph with spaced repetition.
Core engine is LLM-independent. CLI (`spkt`) is the primary interface.

## Repository Structure

```
spikuit/
├── spikuit-core/      # Pure engine (FSRS + NetworkX + APPNP + STDP + LIF)
│   ├── src/spikuit_core/
│   │   ├── models.py      # Neuron, Synapse, Spike, Plasticity (msgspec)
│   │   ├── circuit.py     # Public API: fire, retrieve, ensemble, due
│   │   ├── propagation.py # APPNP spreading + STDP + LIF decay
│   │   └── db.py          # Async SQLite persistence
│   └── tests/             # pytest-asyncio tests
├── spikuit-cli/       # spkt command (Typer)
│   └── src/spikuit_cli/main.py
└── spikuit-agents/    # Future: SDK / adapters
```

## Development Commands

```bash
# Run all tests
uv run --package spikuit-core pytest spikuit-core/tests/ -v

# Run CLI
uv run --package spikuit-cli spkt --help

# Run specific test file
uv run --package spikuit-core pytest spikuit-core/tests/test_propagation.py -v
```

## Conventions

- **Models**: msgspec.Struct with type annotations. No dataclasses.
- **Async**: All DB operations are async (aiosqlite). Circuit methods are async.
- **TDD**: Write tests first, then implement. Tests use pytest-asyncio.
- **Naming**: Neuroscience-inspired (Neuron, Synapse, Spike, Circuit, Plasticity).
- **Language**: Code, comments, docs, skills — all in English.
- **Responses**: Match the user's language when speaking to them.

## spkt CLI

All commands support `--json` for machine-readable output.

| Command | Purpose |
|---------|---------|
| `spkt add` | Add a Neuron |
| `spkt fire` | Fire a Spike (FSRS + APPNP + STDP) |
| `spkt due` | List neurons due for review |
| `spkt retrieve` | Graph-weighted search |
| `spkt list` | List neurons (filter by type/domain) |
| `spkt link` | Create a Synapse |
| `spkt inspect` | Neuron detail |
| `spkt stats` | Circuit statistics |
| `spkt visualize` | Interactive graph visualization (HTML) |

## Grade Scale

| Grade | Meaning | FSRS Rating |
|-------|---------|-------------|
| `miss` | Failed recall | Again |
| `weak` | Uncertain | Hard |
| `fire` | Correct | Good |
| `strong` | Perfect | Easy |

## Synapse Types

| Type | Direction | Use |
|------|-----------|-----|
| `requires` | Directed | A requires understanding B |
| `extends` | Directed | A extends B |
| `contrasts` | Bidirectional | A contrasts with B |
| `relates_to` | Bidirectional | General association |

## Key Algorithms

- **APPNP**: Personalized PageRank propagation. Activation flows along outgoing edges.
- **STDP**: Edge weights update based on co-fire timing (tau_stdp = 7 days).
- **LIF**: Pressure accumulates from neighbor fires, decays exponentially (tau_m = 14 days).
- **FSRS**: Per-neuron spaced repetition. Propagation only affects pressure, never stability/difficulty.
