# Spikuit

[English](README.md) | [日本語](docs/README.ja.md)

**Synapse-inspired spaced repetition engine**

FSRS × Knowledge Graph × Spreading Activation

---

## What is Spikuit?

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a spaced repetition system that models memory as a neural circuit. When you review a concept, activation propagates through connected knowledge — strengthening pathways you use, letting unused ones fade.

**Just study. The knowledge graph builds itself.**

No manual note-taking. No link management. No folder organization.
Review a concept, and the graph grows and adapts around what you know.

### Motivation

Great tools already exist — Spikuit builds on where they intersect:

| Tool | Strength | Spikuit adds |
|------|----------|-------------|
| Anki | Best-in-class scheduling | Concept relationships + graph-aware retrieval |
| Obsidian | Rich knowledge linking | Spaced repetition + adaptive weighting |
| DeepTutor | Context-aware tutoring | Long-term retention via FSRS |

Spikuit combines these ideas: **Learn → Retain → Retrieve** in a single flow.

## The Neuron Model

Spikuit maps directly to neuroscience:

| Brain | Spikuit | Role |
|-------|---------|------|
| Neuron | `Neuron` | A unit of knowledge (Markdown) |
| Synapse | `Synapse` | Typed, weighted connection |
| Spike | `Spike` | A review event (action potential) |
| Circuit | `Circuit` | The full knowledge graph |
| Plasticity | `Plasticity` | Tunable learning parameters |

## Algorithms

| Algorithm | Inspiration | What it does |
|-----------|------------|--------------|
| **FSRS** | Evidence-based scheduling | Per-neuron spaced repetition |
| **APPNP** | Personalized PageRank | Review one node, activate its neighbors |
| **STDP** | Spike-Timing-Dependent Plasticity | Connections strengthen when reviewed together |
| **LIF** | Leaky Integrate-and-Fire | Review pressure accumulates and decays |
| **Graph-weighted Retrieve** | Brain PageRank | Search ranked by relevance × memory strength × centrality |

## Quick Start

```bash
# Install
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-cli

# Add knowledge
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
spkt add "# Monad\n\nA monoid in the category of endofunctors." -t concept -d math

# Connect them
spkt link <neuron-a> <neuron-b> --type requires

# Review
spkt fire <neuron-id> --grade fire

# What's due?
spkt due

# Search (ranked by FSRS retrievability + graph centrality + pressure)
spkt retrieve "functor"

# Visualize
spkt visualize
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `spkt add` | Add a Neuron |
| `spkt fire` | Fire a Spike (review + propagation + STDP) |
| `spkt due` | Show neurons due for review |
| `spkt retrieve` | Graph-weighted search |
| `spkt list` | List neurons (filter by type/domain) |
| `spkt link` | Create a Synapse |
| `spkt inspect` | Neuron detail: FSRS state, pressure, neighbors |
| `spkt stats` | Circuit statistics |
| `spkt visualize` | Interactive graph visualization (HTML) |

## Architecture

```
spikuit/
├── spikuit-core/      # LLM-independent engine
│   ├── models.py      #   Neuron, Synapse, Spike, Plasticity (msgspec)
│   ├── circuit.py     #   Public API: fire, retrieve, ensemble, due
│   ├── propagation.py #   APPNP spreading + STDP + LIF decay
│   └── db.py          #   Async SQLite persistence
├── spikuit-cli/       # spkt command (Typer)
└── spikuit-agents/    # Quiz generation layer (planned)
```

### How `fire()` works

```
circuit.fire(spike)
  1. Record spike to DB
  2. FSRS: update stability, difficulty, schedule next review
  3. APPNP: propagate activation to neighbors (pressure deltas)
  4. Reset source neuron pressure
  5. STDP: update edge weights based on co-fire timing
  6. Record last-fire timestamp for future STDP
```

### Tech Stack

- **Models**: msgspec.Struct (type-safe, fast serialization)
- **Storage**: SQLite (aiosqlite) + NetworkX (in-memory graph)
- **Scheduling**: FSRS v6
- **CLI**: Typer
- **Visualization**: pyvis (vis.js)
- **Language**: Python 3.11+

## Development

```bash
# Setup
uv sync --package spikuit-core --extra dev

# Run tests (56 tests)
uv run --package spikuit-core pytest spikuit-core/tests/ -v

# CLI dev
uv run --package spikuit-cli spkt --help
```

## License

Apache-2.0
