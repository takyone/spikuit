# CLI Reference

All commands support `--json` for machine-readable output.

## Global Options

Most commands accept these flags:

| Option | Description |
|--------|-------------|
| `--brain`, `-b` | Brain root directory (overrides auto-discovery) |
| `--json` | Machine-readable JSON output |

## Brain Management

### `spkt init`

Initialize a new Brain in the current directory. Without flags, starts an
interactive wizard. With `--json` or explicit `--provider`, runs non-interactively.

```
$ spkt init

Brain name [my-project]:
Configure embeddings? [y/N]: y
  Providers: openai-compat, ollama
  Provider [openai-compat]:
  Base URL [http://localhost:1234/v1]:
  Model [text-embedding-nomic-embed-text-v1.5]:
  Dimension [768]:

--- Summary ---
...
Create brain? [Y/n]:
```

Non-interactive (for scripts and agents):

```bash
spkt init -p none                      # No embeddings
spkt init --name my-brain -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5
spkt init -p ollama --json             # JSON output for agents
```

### `spkt config`

Show the current brain configuration.

```bash
spkt config
spkt config --json
```

### `spkt embed-all`

Backfill embeddings for existing neurons that don't have one yet.

```bash
spkt embed-all
```

## Knowledge Management

### `spkt add`

Add a new Neuron to the circuit.

```bash
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
spkt add "Content here" --type fact --domain physics --source "textbook p.42"
```

| Option | Description |
|--------|-------------|
| `-t`, `--type` | Neuron type (e.g. `concept`, `fact`, `procedure`) |
| `-d`, `--domain` | Knowledge domain (e.g. `math`, `french`) |
| `-s`, `--source` | Origin URL or reference |

### `spkt list`

List neurons with optional filters.

```bash
spkt list
spkt list -t concept -d math
spkt list --limit 50
```

### `spkt inspect`

Show detailed information about a neuron: content, FSRS state,
pressure, and connected synapses.

```bash
spkt inspect <neuron-id>
spkt inspect <neuron-id> --json
```

### `spkt link`

Create a synapse between two neurons.

```bash
spkt link <pre-id> <post-id> --type requires
spkt link <a-id> <b-id> --type relates_to
```

| Type | Direction | Use |
|------|-----------|-----|
| `requires` | Directed | A requires understanding B |
| `extends` | Directed | A extends B |
| `contrasts` | Bidirectional | A contrasts with B |
| `relates_to` | Bidirectional | General association |

## Review

### `spkt fire`

Record a review event (fire a spike).

```bash
spkt fire <neuron-id> --grade fire
spkt fire <neuron-id> -g strong
```

| Grade | Meaning | FSRS Rating |
|-------|---------|-------------|
| `miss` | Failed recall | Again |
| `weak` | Uncertain | Hard |
| `fire` | Correct | Good |
| `strong` | Perfect | Easy |

### `spkt due`

Show neurons due for review.

```bash
spkt due
spkt due -n 20
spkt due --json
```

### `spkt quiz`

Interactive flashcard review session. Presents due neurons with
scaffold-adaptive content and accepts self-grading.

```bash
spkt quiz
spkt quiz --limit 10
```

## Search

### `spkt retrieve`

Graph-weighted search combining keyword matching, semantic similarity,
FSRS retrievability, graph centrality, and review pressure.

```bash
spkt retrieve "category theory"
spkt retrieve "functor" --limit 5
```

## Visualization

### `spkt visualize`

Generate an interactive HTML graph visualization.

```bash
spkt visualize
spkt visualize -o my-graph.html
```

## Statistics

### `spkt stats`

Show circuit statistics: neuron count, synapse count, graph density.

```bash
spkt stats
spkt stats --json
```
