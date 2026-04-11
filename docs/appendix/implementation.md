# Implementation Details

## APPNP Propagation

Personalized PageRank spreading:

```
Z = (1 - alpha) * A_hat @ Z + alpha * H
```

- `alpha` = teleport probability (higher = more local, default: 0.15)
- `A_hat` = normalized adjacency with self-loops
- `H` = initial activation (grade-dependent)

## STDP Edge Weight Updates

Edge weights update from co-fire timing within `tau_stdp` days:

- Pre before post (LTP): `dw = +a_plus * exp(-|dt| / tau)`
- Post before pre (LTD): `dw = -a_minus * exp(-|dt| / tau)`

## LIF Pressure Model

Pressure accumulates from neighbor fires, decays exponentially:

```
pressure(t) = pressure * exp(-dt / tau_m)
```

## How `fire()` works

```
circuit.fire(spike)
  1. Record spike to DB
  2. FSRS: update stability, difficulty, schedule next review
  3. APPNP: propagate activation to neighbors (pressure deltas)
  4. Reset source neuron pressure
  5. STDP: update edge weights based on co-fire timing
  6. Record last-fire timestamp for future STDP
```

## Plasticity Parameters

| Parameter | Default | What it controls |
|-----------|---------|-----------------|
| `alpha` | 0.15 | APPNP teleport probability (locality) |
| `propagation_steps` | 5 | APPNP iteration count |
| `tau_stdp` | 7.0 | STDP time window (days) |
| `a_plus` | 0.03 | STDP LTP amplitude |
| `a_minus` | 0.036 | STDP LTD amplitude |
| `tau_m` | 14.0 | LIF membrane time constant (days) |
| `pressure_threshold` | 0.8 | LIF pressure threshold |
| `weight_floor` | 0.05 | Minimum edge weight |
| `weight_ceiling` | 1.0 | Maximum edge weight |

## Embedding Pipeline

### Input Preparation

Before embedding, neuron content goes through a preparation pipeline:

```
Raw neuron content
  → strip YAML frontmatter
  → prepend [Section: ...] from frontmatter (if present)
  → prepend [key: value] from source searchable metadata (truncated to max_searchable_chars)
  → final embedding input
```

This ensures embeddings capture semantic context beyond the raw text,
while excluding structural noise (frontmatter keys, formatting).

### Task-Type Prefixes

Many embedding models perform better when the input is tagged with its
purpose (document vs. query). Spikuit supports this via `prefix_style`
in `config.toml`:

```toml
[embedder]
prefix_style = "nomic"    # "nomic", "google", "cohere", "none"
```

| Style | Document prefix | Query prefix |
|-------|----------------|--------------|
| `nomic` | `search_document: ` | `search_query: ` |
| `google` | `RETRIEVAL_DOCUMENT: ` | `RETRIEVAL_QUERY: ` |
| `cohere` | `search_document: ` | `search_query: ` |
| `none` (default) | — | — |

The prefix is applied automatically:
- `EmbeddingType.DOCUMENT` when adding/updating neurons and running `embed-all`
- `EmbeddingType.QUERY` when calling `retrieve()`

### Searchable Metadata Formula

When a neuron has source searchable metadata, the embedding input becomes:

```
[key1: value1] [key2: value2] [Section: section_name] body_text
```

Total searchable content is truncated to `max_searchable_chars` (default: 500)
to prevent metadata from dominating the embedding.

## Embedder Providers

| Provider | API | Use case |
|----------|-----|----------|
| `openai-compat` | `/v1/embeddings` | LM Studio, Ollama /v1, vLLM, OpenAI |
| `ollama` | `/api/embed` | Ollama native API |
| `none` | — | No embeddings (keyword-only search) |

## Neuron Model Mapping

| Brain | Spikuit | Role |
|-------|---------|------|
| Neuron | `Neuron` | A unit of knowledge (Markdown) |
| Synapse | `Synapse` | Typed, weighted connection |
| Spike | `Spike` | A review event (action potential) |
| Circuit | `Circuit` | The full knowledge graph |
| Plasticity | `Plasticity` | Tunable learning parameters |

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
