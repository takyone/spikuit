# Spikuit

**A knowledge base that gets smarter the more you use it.**

---

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a personal knowledge system
where **searching, reviewing, and asking questions all make the system better** —
automatically.

## What can you do with it?

### /learn → /qabot : Self-improving RAG

Feed articles, notes, or URLs into your brain, then query it with
natural language. Answers include source citations. Retrieval quality
improves with every conversation — unhelpful results are automatically
penalized, helpful ones are boosted.

```
You: /learn
     Summarize this for my brain: https://arxiv.org/abs/1706.03762

Agent: Ingested 8 neurons from "Attention Is All You Need".
       Connected to existing knowledge. Source attached for citation.

You: /qabot
     How does multi-head attention differ from single-head?

Agent: Multi-head attention runs multiple attention functions in parallel...
       Sources:
       - [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
```

### /learn → /tutor : AI study partner

Build a knowledge graph from your study material, then let an AI tutor
teach, quiz, and coach you. It detects prerequisites, adapts difficulty,
and gives feedback on mistakes — not just "correct" or "wrong".

```
You: /learn
     I'm studying category theory. Key concepts:
     - Functor: maps between categories preserving structure
     - Natural Transformation: morphism between functors
     - Monad: monoid in the category of endofunctors

Agent: Created 3 neurons. Connected: Monad --requires--> Functor

You: /tutor

Tutor: Let's start with Functor — it's a prerequisite for the other two.
       [teaches, quizzes, gives feedback, re-explains weak areas]
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
# Configures embeddings and installs Agent CLI skills (/tutor, /learn, /qabot)
spkt init
```

Then, from your Agent CLI (Claude Code, Cursor, Codex):

```
/learn    → Add knowledge from conversation, notes, or URLs
/qabot    → Ask questions — get cited answers from your knowledge graph
/tutor    → Study with an AI tutor that adapts to your level
```

Or use `spkt` commands directly:

```bash
spkt learn "https://example.com/article" -d cs --json
spkt retrieve "query"
spkt communities --detect
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
