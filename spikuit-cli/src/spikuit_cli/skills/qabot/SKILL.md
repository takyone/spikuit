---
name: qabot
description: Ask questions about your Spikuit brain and get answers from your knowledge graph. Retrieval quality improves as you chat — helpful results get boosted, unhelpful ones get penalized. Use when you want to search or ask questions about stored knowledge.
allowed-tools: Bash(spkt *)
---

# Knowledge Q&A Session

Answer questions using the user's Spikuit brain. Retrieval improves through feedback.

## Brain State

Stats: !`spkt stats --json 2>/dev/null || echo '{}'`

## Flow

1. User asks a question
2. Retrieve: `spkt retrieve "<query>" --json`
3. For each result, get context: `spkt inspect <id> --json`
4. Synthesize an answer from retrieved neurons
5. Show answer with source references
6. On follow-up: retrieve again (prior results are implicitly penalized if query is similar)

## Answer Guidelines

- **Synthesize**: combine information from multiple neurons
- **Cite with provenance**: use Source metadata from `spkt inspect --json` for proper citation
- **Acknowledge gaps**: if retrieval doesn't cover the question, say so
- **Match language**: answer in the same language as the question

### Citation Format

`spkt inspect <id> --json` returns a `sources` array with `id`, `url`, and `title`.
When sources are available, cite them with URL. When no sources are attached, cite by neuron ID.

```
[Answer synthesized from retrieved neurons]

Sources:
- [Source Title](https://example.com/paper.pdf) (via n-abc123)
- n-def456: Neuron title (no source URL)
```

## Context Expansion

For each retrieved neuron, also check its neighbors for richer context:
- Prerequisites (via `requires` synapses)
- Related concepts (via `relates_to` synapses)
- Contrasts (via `contrasts` synapses)

## Feedback Signals

- **Similar follow-up question** → prior results weren't good enough
- **User says "thanks" / "good"** → results were helpful, note which ones
- **Topic change** → start fresh context

## Commands

```bash
spkt retrieve "<query>" --json
spkt inspect <id> --json            # includes sources[] and community_id
spkt communities --json             # view community structure
```
