# Concepts

## Architecture

```
spikuit/
├── spikuit-core/          # LLM-independent engine
│   ├── models.py          #   Neuron, Synapse, Spike, Plasticity, Scaffold
│   ├── circuit.py         #   Public API: fire, retrieve, ensemble, due
│   ├── propagation.py     #   APPNP spreading + STDP + LIF decay
│   ├── db.py              #   Async SQLite + sqlite-vec persistence
│   ├── embedder.py        #   Pluggable embedding providers
│   ├── session.py         #   Session abstraction (QABot, Learn)
│   ├── scaffold.py        #   ZPD-inspired scaffolding
│   ├── learn.py           #   Learn protocol (Flashcard, extensible)
│   └── config.py          #   .spikuit/ brain config and discovery
├── spikuit-cli/           # spkt command (Typer)
└── spikuit-agents/        # Agent adapters (planned)
```

## Algorithms

### FSRS (Free Spaced Repetition Scheduler)

Per-neuron spaced repetition. Each neuron has an FSRS Card that tracks
stability, difficulty, and next review date. Propagation **never** touches
FSRS state -- it only affects pressure.

### APPNP (Approximate Personalized Propagation of Neural Predictions)

When you fire a spike, activation propagates to neighbors via
Personalized PageRank. This creates **review pressure** on related
concepts, suggesting what to study next.

```
Z = (1 - alpha) * A_hat @ Z + alpha * H
```

- `alpha` = teleport probability (higher = more local)
- `A_hat` = normalized adjacency with self-loops
- `H` = initial activation (grade-dependent strength)

### STDP (Spike-Timing-Dependent Plasticity)

Edge weights update based on co-fire timing within `tau_stdp` days:

- **Pre fires before post (LTP)**: `dw = +a_plus * exp(-|dt| / tau)`
- **Post fires before pre (LTD)**: `dw = -a_minus * exp(-|dt| / tau)`

Connections strengthen when you review related concepts together,
weaken when you don't.

### LIF (Leaky Integrate-and-Fire)

Review pressure accumulates from neighbor fires and decays exponentially:

```
pressure(t) = pressure * exp(-dt / tau_m)
```

When pressure exceeds the threshold, the neuron is "ready" for
spontaneous review.

## Sessions

Sessions are interaction modes for the Brain (Circuit). The Brain is the
universal backend; Sessions define how you interact with it.

### QABotSession

Self-optimizing RAG chat. Features:

- **Negative feedback**: similar follow-up queries penalize prior results
- **Accept**: explicit positive feedback boosts neurons
- **Deduplication**: already-returned neurons are excluded
- **Persistent/ephemeral**: choose whether to commit boosts on close

### LearnSession

Conversational knowledge curation. Methods:

- **ingest**: add a neuron and auto-discover related concepts
- **relate**: create or strengthen synapses
- **search**: graph-weighted retrieval
- **merge**: combine duplicate neurons (transfer synapses + content)

### Conversational RAG Curation

The key insight: **conversation directly improves retrieval quality**.

Traditional RAG treats the knowledge base as static. Spikuit's graph is
alive -- every review, accepted result, and curation action refines the
structure. The result is a RAG system that gets better *because you use it*.

## Embedder

Pluggable text embedding with multiple provider support:

| Provider | API | Use case |
|----------|-----|----------|
| `openai-compat` | `/v1/embeddings` | LM Studio, Ollama /v1, vLLM, OpenAI |
| `ollama` | `/api/embed` | Ollama native API |
| `none` | -- | No embeddings (keyword search only) |

Embeddings are stored in sqlite-vec for KNN search and used in the
retrieve scoring formula:

```
score = max(keyword_sim, semantic_sim) * (1 + retrievability + centrality + pressure + boost)
```

## Scaffold

ZPD-inspired (Zone of Proximal Development) support levels computed from
FSRS state and graph neighbors:

| Level | When | What |
|-------|------|------|
| **FULL** | New / Learning state | Max hints, full content, easy questions |
| **GUIDED** | Relearning / low stability | Hints on request, partial content |
| **MINIMAL** | Review with moderate stability | Harder questions, title only |
| **NONE** | High stability (mastered) | Pure recall, application-level |

Scaffold also identifies:

- **Context**: strong neighbors (scaffolding material the learner knows well)
- **Gaps**: weak prerequisites (should study first)

## Learn Protocol

Abstract protocol: select -> scaffold -> present -> evaluate -> record.

- **Flashcard**: self-grade flashcard, no LLM required. Scaffold level
  controls how much content is revealed.
- **Quiz** (via agents): LLM-generated questions with per-neuron grading.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Models | msgspec.Struct |
| Storage | SQLite (aiosqlite) + NetworkX + sqlite-vec |
| Scheduling | FSRS v6 |
| Embeddings | httpx (OpenAI-compat / Ollama) |
| CLI | Typer |
| Visualization | pyvis (vis.js) |
| Language | Python 3.11+ |
