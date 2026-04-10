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

### "I want to remember what I learn"

```
You: /tutor

Tutor: You have 5 concepts due. Let's start with Functor —
       it's a prerequisite for Monad which is also due.
       [teaches the concept, then quizzes you]

You:   [answers]

Tutor: Good, but you mixed up the convergence condition.
       Here's what actually happens: ...
       [re-explains, then tries a different question angle]
```

Review concepts with an AI tutor that adapts to your understanding level.
It doesn't just quiz you — it teaches weak areas, gives feedback on mistakes,
and adjusts difficulty based on how well you know each concept.

### "I want to build a knowledge base that's actually searchable"

```bash
# Add knowledge
spkt add "# Functor\n\nA mapping between categories." -t concept -d math
spkt add "# Monad\n\nA monoid in endofunctors." -t concept -d math

# Search — results ranked by relevance, how well you know each concept,
# and how central it is in your knowledge graph
spkt retrieve "category theory"
```

The more you use it, the better search gets. Concepts you review often
rank higher. Related concepts surface together. Unhelpful results
get pushed down automatically.

### "I want an AI that knows what I know"

```python
from spikuit_core import QABotSession

session = QABotSession(circuit, persist=True)
results = await session.ask("What is a functor?")

# Results get better over time:
# - Follow-up questions auto-penalize unhelpful prior results
# - Accepting results boosts them for future queries
# - The graph remembers what's useful across sessions
await session.accept([results[0].neuron_id])
```

Give an AI agent a Spikuit brain, and it can search your knowledge,
add new concepts from conversations, and track what you've mastered
vs. what needs review.

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
