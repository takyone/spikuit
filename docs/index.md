# Spikuit

**Knowledge, curated through conversation.**

> *No preprocessing. No chunking pipelines. No metadata schemas to maintain.
> Just add your documents and talk with your agent.*

---

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a personal knowledge system
where an AI agent handles the hardest parts of knowledge management —
ingestion, structuring, and maintenance — through dialogue.

Traditional RAG systems break down at data curation: chunking, tagging,
connecting, keeping things fresh. Spikuit solves this with
**Conversational Curation** — the agent curates your knowledge base
as you talk to it.

## Three skills, one loop

### `/spkt-teach` — Talk it in.

Feed articles, notes, or URLs into your Brain. The agent chunks content,
discovers relations, and builds your knowledge graph — you just talk.

```
You: /spkt-teach
     Summarize this for my brain: https://arxiv.org/abs/1706.03762

Agent: Added 8 neurons from "Attention Is All You Need".
       6 synapses created, source linked for citation.
```

### `/spkt-qabot` — Ask it back.

Query your Brain with natural language. Answers include source citations.
Retrieval quality improves with every conversation — unhelpful results are
automatically penalized, helpful ones are boosted.

```
You: /spkt-qabot
     How does multi-head attention differ from single-head?

Agent: Multi-head attention runs multiple attention functions in parallel...
       Sources:
       - [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
```

### `/spkt-tutor` — Let it teach you.

An AI tutor built on your knowledge graph. It detects prerequisites,
adapts difficulty, and gives feedback on mistakes — not just "correct"
or "wrong".

```
You: /spkt-tutor

Tutor: Let's start with Functor — it's a prerequisite for the other two.
       [teaches → quizzes → gives feedback → re-explains weak areas]
```

## How It Works

1. **Smart scheduling** — each concept has its own review timing
   ([FSRS](https://github.com/open-spaced-repetition/fsrs4anki))
2. **Activation spreading** — reviewing one concept nudges related
   concepts closer to review. Connections used together get stronger.
3. **Search optimization** — results ranked by relevance × memory
   strength × graph centrality. Feedback improves ranking over time.

## Quick Start

```bash
# Install
pip install spikuit

# Initialize a brain (interactive wizard)
spkt init
```

Then, from your Agent CLI (Claude Code, Cursor, Codex):

```
/spkt-teach    → Talk it in. Curate knowledge through conversation.
/spkt-qabot    → Ask it back. Get cited answers from your knowledge graph.
/spkt-tutor    → Let it teach you. Study with an AI that adapts to your level.
```

Or use `spkt` commands directly:

```bash
spkt source learn ./papers/ -d cs --json     # Ingest a directory with metadata
spkt retrieve "query" --filter domain=math
spkt diagnose                                # Brain health check
spkt consolidate                             # Sleep-inspired graph optimization
spkt export -o brain.json --format json
spkt visualize
```

## Documentation

- [Getting Started](getting-started.md) — install, initialize, first commands
- [How to Use](how-to-use.md) — use cases, agent skills, Python API
- [Concepts](concepts.md) — brain, graph model, how things connect
- [CLI Reference](cli.md) — all `spkt` commands
- [Appendix](appendix.md) — algorithms and technical details
- [API Reference](reference/index.md) — Python API documentation

## License

Apache-2.0
