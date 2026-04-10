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
# Graph-weighted search (keyword + semantic + FSRS + centrality)
spkt retrieve "functor"

# List by type/domain
spkt list -t concept -d math

# Inspect a neuron (FSRS state, pressure, neighbors)
spkt inspect <neuron-id>

# Circuit statistics
spkt stats
```

### Visualize

```bash
# Generate interactive HTML graph
spkt visualize -o graph.html
```

## Conversational Sessions (Skills)

Sessions are LLM-powered interaction modes designed to run inside
**Agent CLIs** — tools like [Claude Code](https://docs.anthropic.com/en/docs/claude-code),
[Codex](https://openai.com/index/introducing-codex/), or similar coding agents
that combine LLM reasoning with shell access.

### Why Agent CLIs?

Spikuit's core engine is LLM-independent — `spkt` commands work standalone.
But sessions like tutoring, curation, and review are *conversational*:
they need an LLM to generate questions, grade answers, discover relations,
and adapt to your responses. Agent CLIs provide exactly this:

- **Shell access**: the agent calls `spkt` commands or the Python API directly
- **LLM reasoning**: the agent generates quiz questions, evaluates answers, suggests links
- **Conversation memory**: multi-turn dialogue (hints → retry → next question)
- **Skills/tools**: register session workflows as reusable slash commands

In Claude Code, sessions are registered as **skills** — type `/tutor` and the
agent handles the full tutoring loop. In other Agent CLIs, the same Python API
powers equivalent integrations.

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
│   (Circuit, AutoQuiz, TutorSession)      │
│                   │                      │
│              spkt CLI                    │
└──────────────────────────────────────────┘
```

### `/tutor` — Scaffolded Tutoring

1-on-1 tutoring with hint progression, gap detection, and retry logic.

**What happens:**

1. Selects neurons due for review (or accepts explicit IDs)
2. Detects weak prerequisites (gaps) and queues them first
3. Presents questions adapted to your scaffold level
4. On wrong answers: offers progressive hints, allows retry
5. After max attempts: reveals the answer
6. Records grades via `circuit.fire()` for FSRS scheduling

**Example flow:**

```
> /tutor

Starting tutor session... 5 neurons queued.
Gap detected: "Functor" is a weak prerequisite for "Monad" — reviewing first.

── Functor ──
Q: What is a Functor?

> A mapping?

That's close but incomplete. Here's a hint:
💡 Think about what it maps *between*.

> A mapping between categories that preserves structure

✅ Correct! (Grade: FIRE)

── Monad ──
Q: How does a Monad relate to a Functor?
...
```

### `/learn` — Knowledge Curation

Add neurons, discover relations, merge duplicates through dialogue.

**What happens:**

1. You provide content (text, notes, ideas)
2. `ingest()` creates a neuron and auto-discovers related concepts
3. `relate()` creates or strengthens synapses
4. `merge()` combines duplicate neurons (transfers synapses + content)
5. `search()` finds related knowledge in your graph

**Example flow:**

```
> /learn

What would you like to add?

> The Y combinator enables recursion in lambda calculus
  without named functions.

Added neuron "Y Combinator" (n-a3f2b1).
Found 3 related concepts:
  - "Lambda Calculus" (0.82 similarity)
  - "Fixed Point" (0.71 similarity)
  - "Recursion" (0.68 similarity)

Link to any of these? (yes/no/select)

> yes, all of them

Created 3 synapses (relates_to).

> Actually, Y Combinator *requires* Lambda Calculus

Updated: Y Combinator → Lambda Calculus (requires)
```

### `/review` — Spaced Repetition Review

Review session using AutoQuiz — stored or LLM-generated questions.

**What happens:**

1. Fetches neurons due for review
2. For each neuron:
    - Presents a stored quiz item if available (preview mode)
    - Generates a new question via LLM if needed (generate mode)
    - Falls back to flashcard if no LLM configured
3. Evaluates your answer (LLM grading or self-grade)
4. Records grade → FSRS update → propagation to neighbors

**Example flow:**

```
> /review

5 neurons due for review.

── 1/5: Subjonctif ──
Q: When do you use the subjonctif in French?
   Give two trigger categories with examples.

> After expressions of doubt like "je doute que"
  and emotions like "je suis content que"

✅ Grade: FIRE
   Stability: 8.2 → 14.1 days

── 2/5: Functor ──
Q: What must a Functor preserve?

> ...
```

## Python API

For building custom integrations, agents, or LLM adapters.

### AutoQuiz with Custom LLM

```python
from spikuit_core import AutoQuiz, Circuit, QuizItem, QuizRequest, Grade

# Your LLM integration
async def my_generate(req: QuizRequest) -> QuizItem:
    prompt = f"Generate a question about neuron {req.primary}"
    # ... call your LLM ...
    return QuizItem(question=q, answer=a, hints=[h1, h2])

async def my_grade(item: QuizItem, response: str) -> Grade:
    prompt = f"Grade this answer: {response}\nExpected: {item.answer}"
    # ... call your LLM ...
    return Grade.FIRE  # or MISS/WEAK/STRONG

# Use it
quiz = AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade)
neuron_ids = await quiz.select(limit=5)
for nid in neuron_ids:
    scaffold = quiz.scaffold(nid)
    item = await quiz.present(nid, scaffold)
    # ... show to user, get response ...
    grade = await quiz.evaluate(nid, item, response)
    await quiz.record(nid, grade)
```

### TutorSession Composition

```python
from spikuit_core import TutorSession, AutoQuiz, Flashcard, Circuit

# With Flashcard (no LLM needed)
tutor = TutorSession(circuit, learn=Flashcard(circuit))

# With AutoQuiz (LLM-powered)
tutor = TutorSession(
    circuit,
    learn=AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade),
    max_attempts=3,
)

queue = await tutor.start(limit=5)
while True:
    state = await tutor.teach()
    if state is None:
        break
    print(state.item.question)
    answer = input("> ")
    state = await tutor.respond(answer)
    if state.grade in (Grade.MISS, Grade.WEAK) and tutor.current:
        hint = tutor.hint()
        if hint:
            print(f"Hint: {hint}")
            answer = input("> ")
            state = await tutor.respond(answer)

print(tutor.stats)
```

### QuizItem Persistence

```python
from spikuit_core import QuizItem, QuizItemRole, ScaffoldLevel

# Store a quiz item (M:N with neurons)
item = QuizItem(
    question="What is a Functor?",
    answer="A mapping between categories that preserves structure.",
    hints=["Think about morphisms.", "It maps both objects and arrows."],
    grading_criteria="Must mention categories and structure preservation.",
    scaffold_level=ScaffoldLevel.MINIMAL,
    neuron_ids={
        "n-abc123": QuizItemRole.PRIMARY,
        "n-def456": QuizItemRole.SUPPORTING,
    },
)
await circuit.add_quiz_item(item)

# Retrieve items for a neuron
items = await circuit.get_quiz_items("n-abc123", role=QuizItemRole.PRIMARY)
items = await circuit.get_quiz_items("n-abc123", scaffold_level=ScaffoldLevel.NONE)

# Delete
await circuit.remove_quiz_item(item.id)
```
