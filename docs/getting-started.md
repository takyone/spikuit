# Getting Started

## Installation

```bash
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-cli
```

## Initialize a Brain

A brain is a project-local `.spikuit/` directory (like `.git/`) containing
the config, database, and cache.

```bash
# Basic init (no embeddings)
spkt init

# With local embeddings (LM Studio)
spkt init -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5

# With Ollama
spkt init -p ollama \
  --base-url http://localhost:11434 \
  --model nomic-embed-text

# Check config
spkt config
```

This creates:

```
.spikuit/
├── config.toml    # Brain configuration
├── circuit.db     # SQLite database
└── cache/         # Embedding cache
```

## Add Knowledge

```bash
# Add a concept
spkt add "# Functor\n\nA mapping between categories that preserves structure." \
  -t concept -d math

# Add another
spkt add "# Monad\n\nA monoid in the category of endofunctors." \
  -t concept -d math
```

## Connect Concepts

```bash
# Monad requires understanding Functor
spkt link <monad-id> <functor-id> --type requires

# See the connection
spkt inspect <monad-id>
```

## Review

```bash
# What's due for review?
spkt due

# Review a concept (grade: miss/weak/fire/strong)
spkt fire <neuron-id> --grade fire

# Interactive quiz session
spkt quiz
```

## Search

```bash
# Graph-weighted search
spkt retrieve "category theory"

# Backfill embeddings for semantic search
spkt embed-all
```

## Visualize

```bash
# Generate interactive HTML graph
spkt visualize
```

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
