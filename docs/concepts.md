# Concepts

## Brain

A **Brain** is a self-contained knowledge space — like an
[Obsidian vault](https://obsidian.md/) or a git repository.
Each Brain lives in a `.spikuit/` directory and contains its own
knowledge graph, configuration, and review schedule.

```
my-project/
└── .spikuit/
    ├── config.toml    # Brain configuration (name, embedder)
    ├── circuit.db     # SQLite database (neurons, synapses, FSRS)
    └── cache/         # Embedding cache
```

### Multiple Brains

You can have as many Brains as you want — one per project, domain, or topic.

```bash
~/math/.spikuit/      # Category theory, algebra
~/french/.spikuit/    # French vocabulary and grammar
~/work/.spikuit/      # Work-related knowledge
```

### Discovery

Like git, `spkt` walks up from the current directory to find `.spikuit/`.
To operate on a different Brain, use `--brain <path>`.

## Knowledge Graph

Spikuit organizes knowledge as a **graph**: concepts are nodes,
relationships are edges.

### Neurons

A **Neuron** is a single unit of knowledge — stored as Markdown.
Each neuron can have a type (concept, term, procedure, etc.) and
a domain (math, french, cs, etc.).

```bash
spkt neuron add "# Functor\n\nA mapping between categories." -t concept -d math
```

### Synapses

A **Synapse** is a typed connection between two neurons.

| Type | Direction | Meaning |
|------|-----------|---------|
| `requires` | A → B | A requires understanding B |
| `extends` | A → B | A builds on B |
| `contrasts` | A ↔ B | A and B are alternatives or opposites |
| `relates_to` | A ↔ B | General association |
| `summarizes` | A → B | Community summary → member |

Connections have weights that **strengthen or weaken over time**
based on how you use them. Review two connected concepts close
together, and their connection gets stronger.

### Sources

A **Source** tracks where knowledge came from — a URL, paper, book,
or file. Sources enable citation in answers and version tracking.

```bash
spkt neuron add "# Key Finding" --source-url "https://paper.com" --source-title "Paper"
spkt source ingest "https://paper.com" -d cs --json    # bulk ingestion
spkt source ingest ./papers/ -d cs --json              # directory ingestion
```

One source can produce many neurons (1:N). Multiple neurons can share
the same source (M:N). Sources are deduplicated by URL.

#### Metadata Layers

Sources carry two kinds of metadata:

| Layer | Purpose | How it's used |
|-------|---------|---------------|
| **filterable** | Structured key-value pairs for strict filtering | SQL WHERE — missing key excludes the result |
| **searchable** | Free-text metadata for soft relevance | Prepended to embedding input — improves semantic match |

```jsonl
{"file_name": "paper.md", "filterable": {"year": "2024", "venue": "NeurIPS"}, "searchable": {"abstract": "We propose..."}}
```

Filterable metadata is strict: `--filter year=2024` only returns sources that
have a `year` key with value `2024`. Sources without the key are excluded entirely.

Searchable metadata is soft: it's prepended to the neuron's content before
embedding, so the embedding captures the metadata's meaning.

#### Source Freshness

URL sources track when they were last fetched and can detect staleness:

```bash
spkt source refresh --stale 30           # Re-fetch sources older than 30 days
spkt source refresh <source-id>          # Re-fetch a specific source
```

Freshness tracking uses conditional GET (ETag / Last-Modified) to minimize
bandwidth. If content has changed, affected neurons are re-embedded automatically.
Sources returning 404 are flagged as `unreachable`.

### Communities

Spikuit detects **communities** — clusters of densely connected neurons —
using the Louvain algorithm. Communities improve retrieval by boosting
results from the same cluster as your top hits.

```bash
spkt community detect                      # Detect communities
spkt community detect --summarize          # Also generate summary neurons
spkt community list --json                 # View current assignment
```

Communities also drive the **visualization** — nodes are color-coded
by community for easy visual identification of knowledge clusters.

### Consolidation

Over time, knowledge graphs accumulate weak connections and unused synapses.
Spikuit provides **sleep-inspired consolidation** — modeled on how the brain
reorganizes knowledge during sleep:

- **SHY (Synaptic Homeostasis)**: Globally downscales weak connection weights
- **SWS (Slow-Wave Sleep)**: Prunes connections that have decayed below threshold
- **REM**: Detects consolidation opportunities (planned)

```bash
spkt consolidate              # Dry-run — see the plan
spkt consolidate apply        # Apply the plan
```

### Why a graph?

Flat flashcard decks treat each card independently. But knowledge
isn't independent — understanding "Monad" requires understanding
"Functor" first. A graph captures these relationships, enabling:

- **Prerequisite detection**: know what to study first
- **Activation spreading**: reviewing one concept nudges related ones
- **Smarter search**: results ranked by graph structure, not just text similarity

## Spaced Repetition

Each neuron has its own review schedule, powered by
[FSRS](https://github.com/open-spaced-repetition/fsrs4anki) —
the same algorithm used in modern Anki.

| Grade | Meaning |
|-------|---------|
| `miss` | Didn't remember |
| `weak` | Uncertain |
| `fire` | Got it right |
| `strong` | Perfect recall |

When you review a concept, two things happen:

1. **Its schedule updates** — stability increases on correct recall,
   decreases on failure
2. **Related concepts get nudged** — reviewing "Functor" pushes "Monad"
   slightly closer to its review time

This means your review queue is influenced by the *structure* of your
knowledge, not just individual due dates.

## Search

Search in Spikuit combines multiple signals:

```
relevance = text_similarity × (1 + memory_strength + centrality + pressure + feedback + community_boost)
```

- **Text similarity**: keyword + semantic (embedding-based)
- **Memory strength**: concepts you know well rank higher
- **Centrality**: well-connected concepts rank higher
- **Pressure**: concepts "primed" by recent reviews rank higher
- **Feedback**: past search feedback (accepted/rejected) adjusts ranking
- **Community boost**: results from the same community as top hits get a boost

This means the same query can return different results over time as
your knowledge and usage patterns evolve.

## Scaffolding

Spikuit adapts to your level of understanding for each concept:

| Level | When | What it means |
|-------|------|--------------|
| Full | New concept | Maximum support — full context, easy questions |
| Guided | Still learning | Some support — hints available, moderate difficulty |
| Minimal | Getting comfortable | Less hand-holding — harder questions |
| None | Mastered | Recall from memory — application-level challenges |

The system also detects **gaps** — prerequisites you haven't mastered yet —
and suggests reviewing them first.

## Sessions

Sessions are LLM-powered interaction modes for your Brain:

| Session | What it does |
|---------|-------------|
| **QABotSession** | RAG chat — ask questions, get answers from your knowledge. Retrieval quality improves through feedback. |
| **IngestSession** | Add knowledge through conversation — auto-discovers relations, detects duplicates. |
| **TutorSession** | AI tutor — diagnoses gaps, teaches concepts, quizzes, gives feedback. |

Sessions can be **persistent** (feedback saved for future use) or
**ephemeral** (discarded after the session).

## Export & Deployment

### QABot Bundle

A **QABot bundle** is a portable, read-only SQLite file that contains
everything needed for retrieval: neurons, synapses, embeddings, and
source citations.

```bash
spkt export --format qabot -o qa-bundle.db
```

It excludes FSRS scheduling state, review history, and raw source files —
just the knowledge and the vectors needed to search it.

Load a bundle with `Circuit(read_only=True)`:

```python
circuit = Circuit(db_path="qa-bundle.db", read_only=True)
results = await circuit.retrieve("query")  # works
await circuit.add_neuron(...)              # raises ReadOnlyError
```

Use cases: deploy a QABot to a server, share a brain without review data,
or build a static RAG endpoint.

### Other Formats

| Format | Command | Use case |
|--------|---------|----------|
| Tarball | `spkt export -o backup.tar.gz` | Full backup |
| JSON | `spkt export --format json -o brain.json` | Sharing, inspection |

## Architecture

```
spikuit-core/     # Pure engine (no LLM dependency)
├── Circuit       #   Knowledge graph + FSRS + propagation
├── Embedder      #   Pluggable text embedding (task-type prefixes)
├── Sessions      #   QABot, Ingest, Tutor
└── Quiz          #   Quiz strategies (Flashcard, AutoQuiz)

spikuit-cli/      # spkt command (Typer)
spikuit-agents/   # Agent skills and adapters
```

The core engine is **LLM-independent** — all `spkt` commands work without
an LLM. Sessions and agent skills add LLM-powered interactions on top.

For algorithm details (FSRS, graph propagation, scoring formulas, embedding
pipeline), see [Appendix: Algorithms](appendix/index.md).
