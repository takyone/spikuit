# Spikuit

[English](README.md) | [日本語](docs/index.ja.md)

**A knowledge base that gets smarter the more you use it.**

---

## What is Spikuit?

Spikuit (spike + circuit, pronounced /spaɪ.kɪt/) is a personal knowledge system
built around one idea: **your knowledge base should learn from you, not just store things.**

Every time you search, review, or ask a question, Spikuit quietly adapts —
boosting what's useful, connecting related ideas, and surfacing what
you're about to forget.

It works as:

- **A self-improving knowledge base** — search quality gets better through usage, not re-indexing
- **A study partner** — an AI tutor that teaches, quizzes, and coaches based on what you actually know
- **An agent's brain** — a knowledge graph that AI agents can read, write, and learn from

### What makes it different?

| | Anki | Obsidian + SRS | Spikuit |
|---|---|---|---|
| Scheduling | Per-card | Per-note | Per-concept, connected |
| Knowledge structure | Flat deck | Manual links | Auto-growing graph |
| Search | Keyword | Keyword + tags | Semantic + graph-weighted |
| Retrieval quality | Static | Static | Improves with usage |
| AI integration | Limited | Plugins | Built-in (agent-native) |

Spikuit doesn't replace these tools — it explores what becomes possible when
you combine a knowledge graph, spaced repetition, and AI agents into one system.

## Use Cases

### /learn → /qabot : Self-improving RAG

Feed sources into your brain, then query it. Retrieval quality improves
with every conversation — no re-indexing needed.

```
You: /learn
     Here's an article on attention mechanisms: https://arxiv.org/abs/1706.03762

Agent: Added 8 neurons (Multi-Head Attention, Scaled Dot-Product, ...).
       6 synapses created, source linked for citation.

You: /qabot
     How does multi-head attention differ from single-head?

Agent: Multi-head attention runs multiple attention functions in parallel,
       each with different learned projections...

       Sources:
       - [Attention Is All You Need](https://arxiv.org/abs/1706.03762) (via n-a1b2c3)

You: What about computational cost?

Agent: [prior results auto-penalized, new neurons retrieved]
```

### /learn → /tutor : AI study partner

Build a knowledge graph from your study material, then let an AI tutor
teach, quiz, and coach you based on what you actually know.

```
You: /learn
     I'm studying category theory. Key concepts:
     - A Functor maps between categories preserving structure
     - A Natural Transformation is a morphism between functors
     - A Monad is a monoid in the category of endofunctors

Agent: Added 3 neurons, 2 synapses (Monad/NatTrans --requires--> Functor).

You: /tutor

Tutor: You have 3 new concepts. Let's start with Functor —
       it's a prerequisite for the other two.
       [teaches, then quizzes]

You: It's like... a mapping that keeps the structure?

Tutor: Right direction, but incomplete. A functor maps both objects
       AND morphisms, and must preserve composition and identity.
       Can you give an example of a functor between two concrete categories?
```

## How It Works (in brief)

Spikuit organizes knowledge as a **graph** — concepts are nodes,
relationships are edges. When you interact with the graph, three
things happen automatically:

1. **Smart scheduling** — each concept has its own review timing based on
   how well you know it (powered by [FSRS](https://github.com/open-spaced-repetition/fsrs4anki))
2. **Activation spreading** — reviewing one concept nudges related concepts
   closer to their review time. Connections that are used together get stronger.
3. **Search optimization** — results are ranked by relevance × how well you know
   each concept × how central it is in your graph. Feedback from conversations
   continuously improves ranking.

For the technical details behind these mechanisms, see
[Appendix: Algorithms](docs/appendix.md).

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
You: /learn
     I want to study Rust's ownership model. Here are my notes: ...

You: /qabot
     When does Rust drop a value?

You: /tutor
     Quiz me on what I learned
```

Or use `spkt` commands directly:

```bash
spkt learn "https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html" -d cs --json
spkt retrieve "ownership borrow"
spkt communities --detect
spkt visualize
```

## Documentation

- [Getting Started](docs/getting-started.md) — install, init, first commands
- [How to Use](docs/how-to-use.md) — use cases, agent skills, Python API
- [Concepts](docs/concepts.md) — brain, graph model, how things connect
- [CLI Reference](docs/cli.md) — all `spkt` commands
- [Appendix: Algorithms](docs/appendix.md) — FSRS, graph propagation, technical details
- [API Reference](https://takyone.github.io/spikuit/reference/) — Python API docs

## Architecture

```
spikuit-core/     # Pure engine (no LLM dependency)
spikuit-cli/      # spkt command
spikuit-agents/   # Agent skills and adapters
```

The core engine is LLM-independent — `spkt` commands work standalone.
Agent skills (`/tutor`, `/learn`, `/qabot`) add LLM-powered interactions
on top, designed for tools like Claude Code.

## Development

```bash
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-core --extra dev
uv run --package spikuit-core pytest spikuit-core/tests/ -v
```

## License

Apache-2.0
