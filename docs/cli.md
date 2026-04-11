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
Shows a plan (neuron count + estimated tokens) before proceeding.

```bash
spkt embed-all              # Interactive — shows plan, asks for confirmation
spkt embed-all --yes        # Skip confirmation
```

## Knowledge Management

### `spkt add`

Add a new Neuron to the circuit.

```bash
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
spkt add "Content here" --type fact --domain physics
spkt add "Content" -t concept --source-url "https://example.com/paper.pdf" --source-title "A Paper"
```

| Option | Description |
|--------|-------------|
| `-t`, `--type` | Neuron type (e.g. `concept`, `fact`, `procedure`) |
| `-d`, `--domain` | Knowledge domain (e.g. `math`, `french`) |
| `--source-url` | Source URL for citation tracking |
| `--source-title` | Source title (used with `--source-url`) |

### `spkt list`

List neurons with optional filters. Also supports metadata and domain discovery.

```bash
spkt list
spkt list -t concept -d math
spkt list --limit 50

# Metadata discovery
spkt list --meta-keys --json          # All filterable/searchable keys across sources
spkt list --meta-values year --json   # Distinct values for a key (with counts)
spkt list --domains --json            # All domains with neuron counts
```

| Option | Description |
|--------|-------------|
| `--meta-keys` | List all metadata keys (filterable + searchable) |
| `--meta-values KEY` | List distinct values for a metadata key |
| `--domains` | List all domains with neuron counts |

### `spkt inspect`

Show detailed information about a neuron: content, FSRS state,
pressure, sources, community, and connected synapses.

```bash
spkt inspect <neuron-id>
spkt inspect <neuron-id> --json    # includes sources[] and community_id
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

## Source Ingestion

### `spkt learn`

Ingest a URL, file, or directory. Creates Source records, extracts content,
and outputs it for agent-driven chunking.

```bash
# Single URL
spkt learn "https://example.com/article" -d cs --json

# Single file
spkt learn ./notes.md -d math --json

# Directory (batch ingestion)
spkt learn ./papers/ -d cs --json
```

| Option | Description |
|--------|-------------|
| `-d`, `--domain` | Domain tag for ingested content |
| `--title` | Override source title (single file/URL only) |
| `--force` | Truncate oversized searchable metadata instead of aborting |

**Directory ingestion** reads all text files (`.md`, `.txt`, `.rst`, `.html`, etc.)
from the directory. Place a `metadata.jsonl` sidecar file to attach metadata:

```jsonl
{"file_name": "paper1.md", "title": "Paper One", "filterable": {"year": "2024", "venue": "NeurIPS"}, "searchable": {"abstract": "We propose..."}}
{"file_name": "paper2.md", "filterable": {"year": "2023"}}
```

If any file's searchable metadata exceeds `max_searchable_chars` (default: 500),
the command aborts with a per-file report. Use `--force` to truncate instead.

## Communities

### `spkt communities`

Show or detect communities (clusters) in the knowledge graph
using the Louvain algorithm.

```bash
spkt communities                   # Show current communities
spkt communities --detect          # Force re-detection
spkt communities --detect -r 2.0   # Higher resolution = more communities
spkt communities --json            # Machine-readable output
```

## Search

### `spkt retrieve`

Graph-weighted search combining keyword matching, semantic similarity,
FSRS retrievability, graph centrality, and review pressure.

```bash
spkt retrieve "category theory"
spkt retrieve "functor" --limit 5

# Filtered retrieval
spkt retrieve "attention" --filter year=2017
spkt retrieve "GNN" --filter domain=cs --filter venue=NeurIPS
```

| Option | Description |
|--------|-------------|
| `--limit`, `-n` | Max results (default: 10) |
| `--filter KEY=VALUE` | Filter by neuron field (`type`, `domain`) or source filterable metadata. Repeatable. Strict: missing key = excluded. |

## Visualization

### `spkt visualize`

Generate an interactive HTML graph visualization.

```bash
spkt visualize
spkt visualize -o my-graph.html
```

## Source Management

### `spkt source list`

List all sources with neuron counts.

```bash
spkt source list
spkt source list --json
```

### `spkt source inspect`

Show source details and attached neurons.

```bash
spkt source inspect <source-id>
spkt source inspect <source-id> --json
```

### `spkt source update`

Update source metadata (URL, title, author).

```bash
spkt source update <source-id> --url "https://new-url.com"
spkt source update <source-id> --title "New Title" --author "Author Name"
```

## Domain Management

### `spkt domain rename`

Rename a domain across all neurons.

```bash
spkt domain rename old-name new-name
```

### `spkt domain merge`

Merge multiple domains into one.

```bash
spkt domain merge domain1 domain2 --into target-domain
```

## Source Freshness

### `spkt refresh`

Re-fetch URL sources to check for content changes. Uses conditional GET
(ETag / Last-Modified) to minimize bandwidth. Updated content triggers
re-embedding of affected neurons.

```bash
spkt refresh <source-id>          # Refresh a specific source
spkt refresh --stale 30           # Refresh sources not fetched in 30+ days
spkt refresh --all                # Refresh all URL sources
```

Sources returning 404 are flagged as `unreachable`.

## Export / Import

### `spkt export`

Export a Brain for backup, sharing, or deployment.

```bash
# Tarball (full backup)
spkt export -o backup.tar.gz

# JSON bundle (portable, human-readable)
spkt export --format json -o brain.json
spkt export --format json --include-embeddings -o brain-full.json

# QABot bundle (read-only SQLite for deployment)
spkt export --format qabot -o qa-bundle.db
```

| Format | Contents | Use case |
|--------|----------|----------|
| `tar` (default) | Full `.spikuit/` directory | Backup, migration |
| `json` | Neurons, synapses, sources as JSON | Sharing, inspection |
| `qabot` | Minimal SQLite with embeddings | Portable RAG deployment |

The **QABot bundle** is a self-contained SQLite file that includes neurons,
synapses, embeddings, and source citations — but excludes FSRS state,
review history, and raw source files. Load it with `Circuit(read_only=True)`.

### `spkt import`

Import a tarball backup.

```bash
spkt import backup.tar.gz
```

## Statistics

### `spkt stats`

Show circuit statistics: neuron count, synapse count, graph density.

```bash
spkt stats
spkt stats --json
```
