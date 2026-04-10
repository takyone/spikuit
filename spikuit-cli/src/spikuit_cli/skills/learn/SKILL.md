---
name: learn
description: Add knowledge to your Spikuit brain through conversation. Structures input into neurons, discovers related concepts, creates connections, and detects duplicates. Use when you want to save or organize knowledge.
allowed-tools: Bash(spkt *)
---

# Knowledge Curation Session

Help the user add and organize knowledge in their Spikuit brain.

## Brain State

Stats: !`spkt stats --json 2>/dev/null || echo '{}'`

## Flow

1. Receive input (text, concept, notes)
2. Structure into Markdown neurons (atomic, self-contained, titled)
3. Check for duplicates: `spkt retrieve "<term>" --json`
4. Add: `spkt add "<content>" -t <type> -d <domain> --json`
5. Discover relations: `spkt retrieve "<content snippet>" --json`
6. Create synapses: `spkt link <new> <related> -t <type>`
7. Confirm with user

## Structuring Rules

- **Atomic**: one concept per neuron (split multi-concept input)
- **Self-contained**: readable without external context
- **Titled**: start with `# Term` or `# Concept Name`

| Input type | How to structure |
|-----------|-----------------|
| Definition | `# Term\n\nDefinition text.` |
| Comparison | Split into separate neurons + contrasts synapse |
| Process | One neuron for process, optionally sub-neurons for steps |
| Conversation excerpt | Extract the key insight, discard filler |

## Type and Domain

Use existing types/domains from the brain. Check with `spkt list --json`.
Common types: concept, term, procedure, pattern, design, language
Common domains: math, cs, french, german, philosophy

## Relation Discovery

After adding, search for related neurons:
```bash
spkt retrieve "<first 200 chars>" --json
```

| Relationship | Synapse type |
|-------------|-------------|
| A requires understanding B | `requires` |
| A extends/builds on B | `extends` |
| A contrasts with B | `contrasts` |
| General association | `relates_to` |

- Prefer specific types over `relates_to`
- Confirm non-obvious connections with the user
- 2-4 connections per neuron is typical

## Duplicate Detection

Before adding, check if the concept exists. If near-duplicate found:
show it, ask: update existing, merge, or add as separate?

## Batch Ingestion

When multiple items at once:
1. Split into atomic concepts
2. Show proposed split for confirmation
3. Add all neurons
4. Discover inter-batch + external relations
5. Create all synapses

## Commands

```bash
spkt add "<content>" -t <type> -d <domain> --json
spkt retrieve "<query>" --json
spkt link <a> <b> -t <type>
spkt list --json
spkt inspect <id> --json
```
