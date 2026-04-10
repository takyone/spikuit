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
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
```

### Synapses

A **Synapse** is a typed connection between two neurons.

| Type | Direction | Meaning |
|------|-----------|---------|
| `requires` | A → B | A requires understanding B |
| `extends` | A → B | A builds on B |
| `contrasts` | A ↔ B | A and B are alternatives or opposites |
| `relates_to` | A ↔ B | General association |

Connections have weights that **strengthen or weaken over time**
based on how you use them. Review two connected concepts close
together, and their connection gets stronger.

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
relevance = text_similarity × (1 + memory_strength + centrality + pressure + feedback)
```

- **Text similarity**: keyword + semantic (embedding-based)
- **Memory strength**: concepts you know well rank higher
- **Centrality**: well-connected concepts rank higher
- **Pressure**: concepts "primed" by recent reviews rank higher
- **Feedback**: past search feedback (accepted/rejected) adjusts ranking

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
| **LearnSession** | Add knowledge through conversation — auto-discovers relations, detects duplicates. |
| **TutorSession** | AI tutor — diagnoses gaps, teaches concepts, quizzes, gives feedback. |

Sessions can be **persistent** (feedback saved for future use) or
**ephemeral** (discarded after the session).

## Architecture

```
spikuit-core/     # Pure engine (no LLM dependency)
├── Circuit       #   Knowledge graph + FSRS + propagation
├── Embedder      #   Pluggable text embedding
├── Sessions      #   QABot, Learn, Tutor
└── Learn         #   Quiz strategies (Flashcard, AutoQuiz)

spikuit-cli/      # spkt command (Typer)
spikuit-agents/   # Agent skills and adapters
```

The core engine is **LLM-independent** — all `spkt` commands work without
an LLM. Sessions and agent skills add LLM-powered interactions on top.

For algorithm details (FSRS, graph propagation, scoring formulas), see
[Appendix: Algorithms](appendix.md).
