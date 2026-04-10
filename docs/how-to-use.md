# How to Use

Use-case-driven guide. For the full command list, see [CLI Reference](cli.md).
For Python API details, see [API Reference](reference/index.md).

## CLI Recipes

### Add Knowledge

```bash
# Simple concept
spkt add "# Functor\n\nA mapping between categories." -t concept -d math

# With frontmatter
spkt add "---
type: concept
domain: french
---
# Subjonctif
Used for doubt, emotion, necessity."

# From a file
cat notes.md | spkt add -t note -d physics
```

### Connect Concepts

```bash
# "Monad requires Functor"
spkt link <monad-id> <functor-id> -t requires

# "HTTP contrasts gRPC" (creates edges in both directions)
spkt link <http-id> <grpc-id> -t contrasts
```

### Review (Flashcard)

```bash
# What's due?
spkt due

# Interactive flashcard session
spkt quiz

# Manual fire (after external review)
spkt fire <neuron-id> -g fire
```

### Search & Explore

```bash
# Graph-weighted search (keyword + semantic + memory strength + centrality)
spkt retrieve "functor"

# List by type/domain
spkt list -t concept -d math

# Inspect a neuron (review state, neighbors)
spkt inspect <neuron-id>

# Circuit statistics
spkt stats
```

### Visualize

```bash
# Generate interactive HTML graph
spkt visualize -o graph.html
```

## Agent Skills

Skills are LLM-powered interaction modes designed to run inside
**Agent CLIs** — tools like [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
or similar coding agents that combine LLM reasoning with shell access.

The core engine is LLM-independent — `spkt` commands work standalone.
Skills add conversational interactions on top: tutoring, curation, and Q&A.

```
┌──────────────────────────────────────────┐
│  Agent CLI (Claude Code, Codex, etc.)    │
│  ┌────────────────┐  ┌───────────────┐   │
│  │  LLM reasoning │  │  Shell access │   │
│  └───────┬────────┘  └───────┬───────┘   │
│          │    Skills / Tools │            │
│          └────────┬──────────┘            │
│                   ▼                      │
│        spikuit-core Python API           │
│   (Circuit, Sessions, Learn)             │
│                   │                      │
│              spkt CLI                    │
└──────────────────────────────────────────┘
```

### `/tutor` — AI Tutor

A 1-on-1 tutor that teaches, quizzes, and coaches — not just a quiz machine.

The tutor decides what to do based on your state: teach a concept you're weak on,
quiz you to check understanding, give feedback on mistakes, or answer your questions.

**Example session:**

```
> /tutor

Tutor: You have 5 concepts due. Functor has low stability and is
       a prerequisite for Monad, so let's start there.

       [LECTURE] A Functor is a mapping between categories that
       preserves structure. Think of it as a box you can map over...
       (explains with examples, using concepts you already know)

       Let me check your understanding.

       [QUIZ] What must a Functor preserve when mapping?

You:   The structure of the category?

Tutor: [FEEDBACK] That's on the right track, but let's be more precise.
       A Functor must preserve identity morphisms and composition.
       So fmap id = id, and fmap (f . g) = fmap f . fmap g.

       Let me try a different angle.

       [QUIZ] In Haskell, why is `fmap` different from `map`?

You:   map only works on lists, fmap works on any Functor?

Tutor: [FEEDBACK] Exactly! `map` is specialized to lists, while `fmap`
       is the generalized version for any Functor instance. ✅ fire
       Stability: 3.2 → 8.1 days

       Now let's move to Monad, which builds on what you just learned...
```

**What the tutor can do:**

| Action | When | Example |
|--------|------|---------|
| Diagnose | Session start | "Functor is weak and blocks Monad — start there" |
| Lecture | New or weak concept | Structured explanation using known concepts as anchors |
| Quiz | After teaching | Varied questions (not just "what is X?") |
| Feedback | After your answer | Explains why right/wrong, what was missing |
| Q&A | You ask a question | Pedagogical answer using your brain's knowledge |
| Drill | Persistent weakness | Focused repetition with varied question angles |

### `/learn` — Knowledge Curation

Add knowledge through conversation. The agent structures your input,
discovers related concepts, and creates connections.

**Example session:**

```
> /learn

What would you like to add?

> Monads in Haskell use bind (>>=) to chain computations.
  IO and Maybe are common examples.

I'll create a neuron:

── Monad ──
# モナド (Monad)
bind (>>=) で計算を連鎖させる。
Examples: IO (side effects), Maybe (failure handling)

Found 2 related concepts:
  1. Functor (0.82) → requires
  2. Applicative (0.78) → requires

Create with these connections? [Y/n]

✅ Added n-abc123, linked to Functor and Applicative
```

**What the agent does:**

- Structures raw input into well-formed Markdown neurons
- Splits multi-concept input into atomic neurons
- Checks for duplicates before adding
- Discovers related existing knowledge and suggests connections
- Proposes types and domains based on existing patterns

### `/qabot` — Knowledge Q&A

Ask questions and get answers from your brain. Retrieval quality
improves through the conversation.

**Example session:**

```
> /qabot

Ask me anything about your brain.

> What's the difference between Functor and Applicative?

A Functor lets you map a function over a wrapped value (fmap).
An Applicative extends this — it lets you apply a wrapped function
to a wrapped value (<*>). Every Applicative is a Functor, but
Applicative adds the ability to combine independent effects...

Sources: n-abc123 (Functor), n-def456 (Applicative), n-ghi789 (Monad)

> Can you go deeper on how Applicative relates to Monad?

[Previous results automatically penalized — retrieves new material]

Over-smoothing occurs when node representations converge as
GCN layers increase. After ~5 layers, all nodes have nearly
identical features...

Sources: n-jkl012 (Deep GNN analysis), n-mno345 (Spectral theory)

> Great, thanks

✅ Accepted: sources boosted for future retrieval
```

**How feedback works:**

- **Similar follow-up** → prior results weren't enough → they get penalized
- **"Thanks" / acceptance** → results were helpful → they get boosted
- **Topic change** → session resets, starts fresh
- **Persistent mode** → feedback survives across sessions

## Python API

For building custom integrations, agents, or LLM adapters.

### AutoQuiz with Custom LLM

```python
from spikuit_core import AutoQuiz, Circuit, QuizItem, QuizRequest, Grade

async def my_generate(req: QuizRequest) -> QuizItem:
    prompt = f"Generate a question about neuron {req.primary}"
    # ... call your LLM ...
    return QuizItem(question=q, answer=a, hints=[h1, h2])

async def my_grade(item: QuizItem, response: str) -> Grade:
    prompt = f"Grade this answer: {response}\nExpected: {item.answer}"
    # ... call your LLM ...
    return Grade.FIRE

quiz = AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade)
```

### TutorSession

```python
from spikuit_core import TutorSession, AutoQuiz, Flashcard

# With Flashcard (no LLM needed)
tutor = TutorSession(circuit, learn=Flashcard(circuit))

# With AutoQuiz (LLM-powered)
tutor = TutorSession(
    circuit,
    learn=AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade),
)

queue = await tutor.start(limit=5)
state = await tutor.teach()
state = await tutor.respond("my answer")
```

### QABotSession

```python
from spikuit_core import QABotSession

session = QABotSession(circuit, persist=True)

# Ask — returns scored, deduplicated results
results = await session.ask("What is a functor?")

# Positive feedback — boost helpful neurons
await session.accept([results[0].neuron_id])

# Follow-up — auto-penalizes prior results if similar
results = await session.ask("functor examples in Haskell?")

await session.close()  # commits boosts to DB
```

### LearnSession

```python
from spikuit_core import LearnSession, SynapseType

session = LearnSession(circuit)

# Add knowledge — auto-discovers related concepts
neuron, related = await session.ingest(
    "# Functor\n\nA mapping between categories.",
    type="concept", domain="math",
)

# Create connections
if related:
    await session.relate(neuron.id, related[0].id, SynapseType.REQUIRES)

# Merge duplicates
await session.merge(["n-old1", "n-old2"], into_id="n-keep")

await session.close()
```
