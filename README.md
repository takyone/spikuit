# Spikuit

[English](README.md) | [日本語](docs/README.ja.md)

**Neural knowledge graph with spaced repetition**

FSRS × Knowledge Graph × Spreading Activation × Conversational RAG

---

## What is Spikuit?

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a knowledge system that models memory as a neural circuit. When you review a concept, activation propagates through connected knowledge — strengthening pathways you use, letting unused ones fade.

It works as both a **human learning tool** and an **Agentic RAG Brain**: the same graph that helps you retain knowledge also powers intelligent retrieval for AI agents.

**Just study. The knowledge graph builds itself.**

No manual note-taking. No link management. No folder organization.
Review a concept, and the graph grows and adapts around what you know.

### Vision

Spikuit brings together ideas from great existing tools:

| Inspired by | What we admire | What Spikuit explores |
|-------------|---------------|----------------------|
| Anki | Best-in-class scheduling | Adding concept relationships on top of scheduling |
| Obsidian | Rich knowledge linking | Combining linking with spaced repetition |
| DeepTutor | Context-aware tutoring | Integrating long-term retention into the loop |

The goal is a system where **Learn → Retain → Retrieve** work as a single flow, complementing these tools rather than replacing them.

### Conversational RAG Curation

Spikuit introduces a novel concept: **tuning RAG quality through conversation**.

Traditional RAG treats the knowledge base as static — you index documents, then query them. Spikuit's knowledge graph is *alive*: every review, every accepted result, every conversation refines the structure. Sessions provide the interaction patterns:

- **QABotSession**: Self-optimizing retrieval. Follow-up queries automatically penalize unhelpful prior results. Accepting results boosts them. The graph learns what's useful.
- **LearnSession**: Conversational knowledge curation. Add neurons through dialogue, discover related concepts, create connections, merge duplicates. The conversation *is* the curation.
- **ReviewSession**: Spaced repetition with scaffold-adaptive presentation. (planned)

The result: a RAG system that gets better *because you use it*, not just when you re-index.

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
| **Semantic Search** | sqlite-vec KNN | Embedding-based similarity search with pluggable providers |

## Quick Start

```bash
# Install
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-cli

# Initialize a brain (creates .spikuit/ in CWD)
spkt init
spkt init -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5

# Add knowledge
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
spkt add "# Monad\n\nA monoid in the category of endofunctors." -t concept -d math

# Connect them
spkt link <neuron-a> <neuron-b> --type requires

# Review
spkt fire <neuron-id> --grade fire

# What's due?
spkt due

# Search (ranked by FSRS retrievability + graph centrality + pressure + semantic similarity)
spkt retrieve "functor"

# Interactive quiz session
spkt quiz

# Visualize
spkt visualize
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `spkt init` | Initialize .spikuit/ brain |
| `spkt config` | Show brain configuration |
| `spkt embed-all` | Backfill embeddings for existing neurons |
| `spkt add` | Add a Neuron |
| `spkt fire` | Fire a Spike (review + propagation + STDP) |
| `spkt due` | Show neurons due for review |
| `spkt retrieve` | Graph-weighted + semantic search |
| `spkt list` | List neurons (filter by type/domain) |
| `spkt link` | Create a Synapse |
| `spkt inspect` | Neuron detail: FSRS state, pressure, neighbors |
| `spkt stats` | Circuit statistics |
| `spkt quiz` | Interactive flashcard review session |
| `spkt visualize` | Interactive graph visualization (HTML) |

All commands support `--json` for machine-readable output.

## Architecture

```
spikuit/
├── spikuit-core/          # LLM-independent engine
│   ├── models.py          #   Neuron, Synapse, Spike, Plasticity, Scaffold (msgspec)
│   ├── circuit.py         #   Public API: fire, retrieve, ensemble, due
│   ├── propagation.py     #   APPNP spreading + STDP + LIF decay
│   ├── db.py              #   Async SQLite + sqlite-vec persistence
│   ├── embedder.py        #   Pluggable embedding (OpenAI-compat, Ollama, Null)
│   ├── session.py         #   Session abstraction (QABot, Learn)
│   ├── scaffold.py        #   ZPD-inspired scaffolding from FSRS state
│   ├── learn.py           #   Learn protocol (Flashcard, extensible)
│   └── config.py          #   .spikuit/ brain config and discovery
├── spikuit-cli/           # spkt command (Typer)
└── spikuit-agents/        # Agent adapters (planned)
```

### Core Concepts

- **Circuit**: The knowledge graph engine — FSRS scheduling + NetworkX graph + propagation + sqlite-vec embeddings
- **Embedder**: Pluggable text embedding (OpenAI-compat for LM Studio/Ollama/vLLM/OpenAI, Ollama native, Null for testing)
- **Session**: Interaction modes for the Brain
  - **QABotSession**: RAG chat with self-optimizing retrieval (negative feedback, accept, dedup, persistent/ephemeral)
  - **LearnSession**: Conversational knowledge curation (ingest, relate, search, merge)
- **Scaffold**: ZPD-inspired support levels (FULL/GUIDED/MINIMAL/NONE) from FSRS state + graph neighbors
- **Learn**: Abstract protocol (select → scaffold → present → evaluate → record)
  - **Flashcard**: Self-grade flashcard, no LLM required

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

### How `retrieve()` works

```
score = max(keyword_sim, semantic_sim) × (1 + retrievability + centrality + pressure + boost)
```

Semantic similarity uses sqlite-vec KNN search when an embedder is configured. Retrieval boost is accumulated through QABotSession feedback.

### Tech Stack

- **Models**: msgspec.Struct (type-safe, fast serialization)
- **Storage**: SQLite (aiosqlite) + NetworkX (in-memory graph) + sqlite-vec (vector search)
- **Scheduling**: FSRS v6
- **Embeddings**: httpx (OpenAI-compat / Ollama providers)
- **CLI**: Typer
- **Visualization**: pyvis (vis.js)
- **Language**: Python 3.11+

## Development

```bash
# Setup
uv sync --package spikuit-core --extra dev

# Run tests (147 tests)
uv run --package spikuit-core pytest spikuit-core/tests/ -v

# CLI dev
uv run --package spikuit-cli spkt --help
```

## License

Apache-2.0
