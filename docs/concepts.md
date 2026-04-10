# Concepts

## Background: Why a Neural Knowledge Graph?

Spikuit's design draws from three fields: **computational neuroscience**,
**cognitive/developmental psychology**, and **graph-based machine learning**.
This section explains the underlying ideas and how Spikuit adapts them.

### From Neuroscience

#### Neurons and Action Potentials

Biological neurons communicate through discrete electrical impulses
called **action potentials** (spikes). A neuron accumulates input from
its neighbors; when it crosses a threshold, it fires and sends a signal
to downstream neurons. This is a binary, all-or-nothing event.

In Spikuit, a **Spike** is a review event. When you review a concept
(fire a spike), the signal propagates to connected knowledge -- just as
action potentials propagate through neural circuits.

#### Synaptic Plasticity and Hebbian Learning

"Neurons that fire together wire together" (Hebb, 1949). Connections
between neurons strengthen when they are activated in close temporal
proximity. This is the biological basis of associative learning.

Spikuit implements this through **STDP** (below): reviewing related
concepts within a time window strengthens the connections between them.

#### Spike-Timing-Dependent Plasticity (STDP)

STDP refines Hebb's rule with temporal asymmetry:

- **Pre fires before post** (causal order): connection strengthens (**LTP**)
- **Post fires before pre** (reverse order): connection weakens (**LTD**)

The magnitude decays exponentially with time difference. This creates
direction-sensitive learning: if you consistently review A before B,
the A-to-B connection strengthens while B-to-A may weaken.

In Spikuit, edge weights update based on co-fire timing within
`tau_stdp` days (default: 7). Studying "Functor" and then "Monad"
the same day strengthens their connection naturally.

#### Leaky Integrate-and-Fire (LIF)

The LIF model describes how neurons accumulate input (integration)
while gradually losing charge (leak). Input from neighbors builds up
membrane potential; if it exceeds a threshold, the neuron fires;
after firing, it resets.

Spikuit uses LIF for **review pressure**: neighbor reviews push a
neuron's pressure up, time makes it decay. High-pressure neurons
are "ready" for review -- the system is telling you this concept
is being activated by related study.

#### Spreading Activation

When a concept is activated in memory, activation spreads to related
concepts through associative links (Collins & Loftus, 1975). This
explains why thinking about "dog" primes "cat" and "bone" but not
"algebra".

Spikuit implements spreading activation via **APPNP** (Personalized
PageRank): reviewing one concept sends activation to its graph
neighbors, weighted by connection strength.

### From Cognitive and Developmental Psychology

#### The Forgetting Curve and Spaced Repetition

Ebbinghaus (1885) demonstrated that memory decays exponentially over
time, but each successful retrieval strengthens the memory trace and
slows future decay. Optimal review timing -- reviewing just before you
would forget -- maximizes retention efficiency.

Spikuit uses **FSRS v6** (Free Spaced Repetition Scheduler) for
per-neuron scheduling. FSRS models each item's **stability** (how long
until 90% recall probability) and **difficulty**, updating them with
each review.

#### The Testing Effect

Actively retrieving information from memory strengthens it more than
re-reading (Roediger & Karpicke, 2006). Even failed retrieval attempts
improve later recall.

This is why Spikuit's Learn protocol is structured as **present then
evaluate**, not just "show content". The Scaffold system controls how
much is revealed, gradually reducing support as mastery increases.

#### Zone of Proximal Development (ZPD) and Scaffolding

Vygotsky (1978) described the ZPD as the gap between what a learner
can do independently and what they can do with guidance. **Scaffolding**
(Wood, Bruner & Ross, 1976) is the temporary support that helps learners
operate within their ZPD -- gradually removed as competence grows.

Spikuit's **Scaffold** system computes support levels from FSRS state:

| Level | FSRS State | Support |
|-------|-----------|---------|
| **FULL** | Learning (new) | Full content, max hints, easy questions |
| **GUIDED** | Relearning / low stability | Partial content, hints available |
| **MINIMAL** | Review, moderate stability | Title only, harder questions |
| **NONE** | Review, high stability | Pure recall, application-level |

It also identifies **context** (strong neighbors as scaffolding material)
and **gaps** (weak prerequisites that should be studied first).

#### Schema Theory

Schemas are mental frameworks that organize knowledge (Bartlett, 1932;
Piaget). New information is easier to learn when it connects to existing
schemas -- a principle called **assimilation**.

Spikuit's knowledge graph is essentially a schema. When you add a new
concept, `LearnSession.ingest()` automatically searches for related
existing knowledge, making it easy to connect new information to your
existing schema.

### From Graph-Based ML

#### PageRank and APPNP

Google's PageRank (Page et al., 1999) scores web pages by the structure
of the link graph. APPNP (Gasteiger et al., 2019) adapts this for
neural networks, using Personalized PageRank with a teleport probability
that keeps propagation local.

Spikuit uses APPNP for two purposes:

1. **Spreading activation**: review one node, and activation flows to neighbors
2. **Retrieve scoring**: centrality (how connected a concept is) contributes to search ranking

---

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

## Algorithms in Spikuit

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

ZPD-inspired support levels computed from FSRS state and graph neighbors:

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
