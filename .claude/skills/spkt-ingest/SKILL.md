---
name: spkt-ingest
description: Teach knowledge to your Spikuit brain through conversation. Structures input into neurons, discovers related concepts, creates connections, and detects duplicates. Use when you want to save or organize knowledge.
allowed-tools: Bash(spkt *)
---

# Knowledge Curation Session

Help the user add and organize knowledge in their Spikuit brain.

## Mandatory: cut a branch before any batch work

Any ingestion that touches more than one neuron — or any `spkt source ingest`
at all — MUST run on an `ingest/<tag>` branch. Never commit a batch directly
to `main`. The user can always reject the result, and rejecting is cheap when
the work is on a throwaway branch.

```bash
spkt branch start <short-tag>      # e.g. papers-2026-04, monad-notes
# ... do the ingest work ...
# show the user a summary
spkt branch finish                 # user confirmed → ff-merge into main
spkt branch abandon                # user rejected → discard the branch
```

If `spkt branch start` fails ("Brain has no git repository"), tell the user
and ask whether to continue without versioning or run `spkt init --git`
on the existing brain.

Skip the branch only for **single** `spkt neuron add` from conversation —
that's cheap to revert with `spkt undo`.

## Brain State

Stats: !`spkt stats --json 2>/dev/null || echo '{}'`

## Flow

### From conversation (default)

1. Receive input (text, concept, notes)
2. Structure into Markdown neurons (atomic, self-contained, titled)
3. Check for duplicates: `spkt retrieve "<term>" --json`
4. Add: `spkt neuron add "<content>" -t <type> -d <domain> --source-url "<url>" --json`
5. Discover relations: `spkt retrieve "<content snippet>" --json`
6. Create synapses: `spkt synapse add <new> <related> -t <type>`
7. Confirm with user

### From URL or file (source ingestion)

1. Fetch content: `spkt source ingest "<url-or-path>" -d <domain> --json`
2. Read the returned `content` and `source_id`
3. Split content into atomic concepts (chunking)
4. For each chunk: `spkt neuron add "<chunk>" -t <type> -d <domain> --source-url "<url>" --json`
5. Discover relations and create synapses as above
6. After communities change significantly: `spkt community detect`

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

Use existing types/domains from the brain. Check with `spkt neuron list --json`.
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
1. **Cut a branch first**: `spkt branch start <tag>`
2. Split into atomic concepts
3. Show proposed split for confirmation
4. Add all neurons (commits land on the ingest branch, not main)
5. Discover inter-batch + external relations
6. Create all synapses
7. Show summary, ask user to confirm
8. **Confirm** → `spkt branch finish` ┃ **reject** → `spkt branch abandon`

## Output Format

Keep output concise. After ingestion, report a single summary line per operation:

```
Added N neurons, M synapses. Source linked.
```

Details:
- **Neuron count**: how many neurons were created
- **Synapse count**: how many connections were discovered and created
- **Source**: mention only when a source was attached (URL or file)
- **Community re-detection**: mention only if run (`Communities re-detected.`)

Do NOT list every neuron ID or synapse individually unless the user asks.
For batch ingestion, show the summary, then offer "Want to see details?" rather than dumping everything.

When confirming with the user before creation, keep it brief:

```
Will add 3 neurons (concept/math) with 4 synapses.
Source: https://example.com/article
Proceed? [Y/n]
```

## Commands

```bash
spkt neuron add "<content>" -t <type> -d <domain> --json
spkt neuron add "<content>" -t <type> -d <domain> --source-url "<url>" --source-title "<title>" --json
spkt source ingest "<url-or-path>" -d <domain> --json    # fetch + create Source
spkt retrieve "<query>" --json
spkt synapse add <a> <b> -t <type>
spkt neuron list --json
spkt neuron inspect <id> --json                         # includes sources[]
spkt community detect --json                            # re-detect after major ingestion
```
