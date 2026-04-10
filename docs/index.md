# Spikuit

**A knowledge base that gets smarter the more you use it.**

---

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a personal knowledge system
where **searching, reviewing, and asking questions all make the system better** —
automatically.

## What can you do with it?

### Build a knowledge graph that grows with you

```bash
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
spkt add "# Monad\n\nA monoid in endofunctors." -t concept -d math
spkt link <monad-id> <functor-id> -t requires
```

Concepts connect to each other. Search results are ranked by relevance,
how well you know each concept, and how central it is in your graph.

### Study with an AI tutor

```
> /tutor

Tutor: "Functor" has low stability and is a prerequisite for "Monad".
       Let me explain Functor first, then we'll test your understanding.
       ...
       [teaches, quizzes, gives feedback, re-explains weak areas]
```

Not just flashcards — a tutor that diagnoses what you need, teaches
concepts, tests understanding, and coaches you through mistakes.

### Power AI agents with your knowledge

```python
session = QABotSession(circuit, persist=True)
results = await session.ask("What is a functor?")
await session.accept([results[0].neuron_id])
# → helpful results get boosted for future queries
```

Retrieval quality improves through conversation feedback — not re-indexing.

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
# Configures embeddings and installs Agent CLI skills (/tutor, /learn, /qabot)
spkt init

# Add knowledge
spkt add "# Functor\n\nA mapping between categories." -t concept -d math

# Review what's due
spkt due
spkt quiz

# Search
spkt retrieve "functor"

# Visualize your knowledge graph
spkt visualize
```

### Agent CLI Skills

`spkt init` can install skills for your Agent CLI (Claude Code, Cursor, Codex).
You can also install them separately:

```bash
spkt skills install                    # Default: .claude/skills/
spkt skills install -t .cursor/skills  # For Cursor
```

Once installed, use `/tutor`, `/learn`, or `/qabot` from your Agent CLI.

## Documentation

- [Getting Started](getting-started.md) — install, initialize, first commands
- [How to Use](how-to-use.md) — use cases, agent skills, Python API
- [Concepts](concepts.md) — brain, graph model, how things connect
- [CLI Reference](cli.md) — all `spkt` commands
- [Appendix](appendix.md) — algorithms and technical details
- [API Reference](reference/index.md) — Python API documentation

## License

Apache-2.0
