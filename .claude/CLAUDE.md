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

## Brain Setup

```bash
spkt init                              # Create .spikuit/ in CWD
spkt init -p openai-compat \           # With LM Studio embeddings
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5
spkt config                            # Show current brain config
spkt embed-all                         # Backfill embeddings for existing neurons
```

Config lives in `.spikuit/config.toml`. CLI auto-discovers `.spikuit/` by walking up from CWD.

## spkt CLI

All commands support `--json` for machine-readable output.

| Command | Purpose |
|---------|---------|
| `spkt init` | Initialize .spikuit/ brain |
| `spkt config` | Show brain configuration |
| `spkt embed-all` | Backfill embeddings |
| `spkt add` | Add a Neuron |
| `spkt fire` | Fire a Spike (FSRS + APPNP + STDP) |
| `spkt due` | List neurons due for review |
| `spkt retrieve` | Graph-weighted search |
| `spkt list` | List neurons (filter by type/domain) |
| `spkt link` | Create a Synapse |
| `spkt inspect` | Neuron detail |
| `spkt stats` | Circuit statistics |
| `spkt quiz` | Interactive flashcard review session |
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

## Architecture

- **Circuit**: The knowledge graph engine (FSRS + NetworkX + propagation + sqlite-vec)
- **Embedder**: Pluggable text embedding (OpenAICompat, Ollama, Null). Auto-embeds on add/update.
- **Session**: Interaction modes for the Brain
  - **QABotSession**: RAG chat with retrieval feedback (negative penalty, accept, dedup, persistent/ephemeral)
  - **ReviewSession**: Spaced repetition (wraps Learn protocol) — planned
  - **LearnSession**: Knowledge ingestion — planned
- **Scaffold**: ZPD-inspired support levels (FULL/GUIDED/MINIMAL/NONE) from FSRS state + graph neighbors
- **Learn**: Abstract protocol (select → scaffold → present → evaluate → record)
  - **Flashcard** (core): Self-grade flashcard, no LLM required
  - **Quiz** (skills): LLM-generated questions, per-neuron grading
- **1 Quiz : N Neurons**: QuizRequest has primary + supporting neurons, QuizResult has per-neuron grades

## Key Algorithms

- **APPNP**: Personalized PageRank propagation. Activation flows along outgoing edges.
- **STDP**: Edge weights update based on co-fire timing (tau_stdp = 7 days).
- **LIF**: Pressure accumulates from neighbor fires, decays exponentially (tau_m = 14 days).
- **FSRS**: Per-neuron spaced repetition. Propagation only affects pressure, never stability/difficulty.
