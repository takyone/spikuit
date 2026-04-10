# [WIP] Spikuit

**Synapse-inspired spaced repetition engine**

FSRS × Knowledge Graph × Spreading Activation

---

## What is Spikuit?

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a next-generation spaced repetition system that models memory as a neural circuit. When you review a concept, activation propagates through connected knowledge — strengthening pathways you use, letting unused ones fade.

### Core Ideas

- **FSRS scheduling** — Evidence-based spaced repetition at the node level
- **Knowledge Graph** — Concepts linked by typed, weighted edges
- **Spreading Activation** — Review one node, activate its neighbors (Hebbian learning)
- **Forgetting Propagation** — Unused pathways weaken over time (LTD)

## Status

Early development. Migrating from internal prototype (tataque).

## Architecture

```
spikuit/
├── spikuit-core/      # FSRS + Knowledge Graph engine (LLM-independent)
├── spikuit-agents/    # Strands-based agent workflows
├── spikuit-cli/       # spkt command
└── spikuit-viz/       # Graph visualization (planned)
```

## License

Apache-2.0
