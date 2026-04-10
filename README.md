# [WIP] Spikuit

**Synapse-inspired spaced repetition engine**

FSRS × Knowledge Graph × Spreading Activation

---

## What is Spikuit?

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a next-generation spaced repetition system that models memory as a neural circuit. When you review a concept, activation propagates through connected knowledge — strengthening pathways you use, letting unused ones fade.

**Just study. The knowledge graph builds itself.**

No manual note-taking. No link management. No folder organization.
Throw in a source, solve the problems, and a searchable knowledge graph emerges naturally.

### The Problem

| Tool | What it does | What it doesn't |
|------|-------------|-----------------|
| Anki | Schedules reviews | No concept relationships |
| Obsidian | Links knowledge | No spaced repetition |
| DeepTutor | Context-aware tutoring | No long-term retention |

Spikuit unifies all three: **Learn → Retain → Retrieve** in a single flow.

### The Neuron Model

Spikuit maps directly to neuroscience:

| Brain | Spikuit | Role |
|-------|---------|------|
| Neuron | `Neuron` | A unit of knowledge |
| Synapse | `Synapse` | Typed, weighted connection between knowledge |
| Spike | `Spike` | A review event (action potential) |
| Circuit | `Circuit` | The full knowledge graph |

### Core Algorithms

- **FSRS** — Evidence-based spaced repetition at the node level
- **APPNP propagation** — Review one node, activate its neighbors (Personalized PageRank)
- **STDP** — Connections strengthen when concepts are reviewed together (Spike-Timing-Dependent Plasticity)
- **BCM homeostasis** — Sliding threshold prevents over-consolidation
- **STC consolidation** — Cluster reviews trigger long-term memory bonus
- **LIF pressure** — Related reviews accumulate "review pressure" on neighboring nodes

## Status

Early development. Migrating from internal prototype.

## Architecture

```
spikuit/
├── spikuit-core/      # LLM-independent engine (FSRS + KG + propagation)
├── spikuit-agents/    # Strands-based agent workflows (quiz gen, extraction)
├── spikuit-cli/       # spkt command
└── spikuit-viz/       # Graph visualization (planned)
```

### Tech Stack

- **Storage**: SQLite (persistence) + NetworkX (in-memory graph)
- **Scheduling**: FSRS
- **Agents**: Strands SDK
- **Language**: Python 3.11+

## License

Apache-2.0
