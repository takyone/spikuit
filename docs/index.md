# Spikuit

**Neural knowledge graph with spaced repetition**

FSRS x Knowledge Graph x Spreading Activation x Conversational RAG

---

Spikuit (spike + circuit, pronounced /spai.kit/) is a knowledge system that models memory as a neural circuit. When you review a concept, activation propagates through connected knowledge -- strengthening pathways you use, letting unused ones fade.

It works as both a **human learning tool** and an **Agentic RAG Brain**: the same graph that helps you retain knowledge also powers intelligent retrieval for AI agents.

## Key Features

- **FSRS scheduling** -- evidence-based spaced repetition per neuron
- **Graph propagation** -- review one concept, activate its neighbors (APPNP + STDP + LIF)
- **Semantic search** -- embedding-based retrieval via sqlite-vec with pluggable providers
- **Self-optimizing RAG** -- retrieval quality improves through conversation feedback
- **Conversational curation** -- build and refine the knowledge graph through dialogue
- **Scaffold-adaptive learning** -- ZPD-inspired support levels from FSRS state + graph context
- **Project-local brains** -- `.spikuit/` config like `.git/`, with CLI discovery

## Quick Links

- [Getting Started](getting-started.md) -- install, init, and first commands
- [Concepts](concepts.md) -- neuron model, algorithms, sessions, and architecture
- [CLI Reference](cli.md) -- all `spkt` commands
- [API Reference](reference/index.md) -- Python API documentation

## The Neuron Model

| Brain | Spikuit | Role |
|-------|---------|------|
| Neuron | `Neuron` | A unit of knowledge (Markdown) |
| Synapse | `Synapse` | Typed, weighted connection |
| Spike | `Spike` | A review event (action potential) |
| Circuit | `Circuit` | The full knowledge graph |
| Plasticity | `Plasticity` | Tunable learning parameters |

## License

Apache-2.0
