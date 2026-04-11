# /spkt-teach — Knowledge Curation Session

Ingest new knowledge, discover connections, and curate the graph.

## Prerequisites

- A Brain must be initialized (`spkt init`)
- The `spkt` CLI must be available

## Session Flow

1. **Receive input**: The user provides knowledge to add — can be:
   - Free text (paste from a conversation, article, or notes)
   - A specific concept/term to define
   - A file or URL to extract knowledge from
2. **Structure the content**: Convert raw input into well-formed Markdown neurons
3. **Ingest neurons**: `spkt neuron add "<content>" -t <type> -d <domain> --source-url "<url>" --json`
4. **Discover relations**: `spkt retrieve "<query>" --json` to find related neurons
5. **Create synapses**: `spkt synapse add <new> <related> -t <type>` for each connection
6. **Confirm with user**: Show what was added and linked, ask for corrections

### Source Ingestion from URL/File

For bulk content from a URL or file:
1. **Fetch**: `spkt source learn "<url-or-path>" -d <domain> --json` — creates Source, returns content
2. **Chunk**: Split the returned content into atomic concepts
3. **Add each chunk**: `spkt neuron add "<chunk>" --source-url "<url>" --json` — auto-attaches Source
4. **Re-detect communities**: `spkt community detect` after major ingestion

## Content Structuring

Transform raw input into Markdown neurons. Each neuron should be:
- **Atomic**: one concept per neuron (split multi-concept input)
- **Self-contained**: readable without external context
- **Titled**: start with `# Term` or `# Concept Name`

### Structuring Rules

| Input type | How to structure |
|-----------|-----------------|
| Definition | `# Term\n\nDefinition text.` |
| Comparison | Split into separate neurons + contrasts synapse |
| Process/Steps | One neuron for the process, optionally sub-neurons for steps |
| Example-heavy | Core concept neuron + examples in body |
| Conversation excerpt | Extract the key insight, discard filler |

### Type and Domain Assignment

Use existing types and domains from the brain when possible. Check with
`spkt neuron list --json` to see what's already in use. If the content doesn't
fit existing categories, propose new ones to the user.

Common types: `concept`, `term`, `procedure`, `pattern`, `design`, `language`
Common domains: `math`, `cs`, `french`, `german`, `philosophy`

## Relation Discovery

After adding a neuron, search for related existing knowledge:

```bash
spkt retrieve "<first 200 chars of content>" --json
```

For each result, evaluate the relationship:

| Relationship | Synapse type | When to use |
|-------------|-------------|-------------|
| A requires understanding B | `requires` | B is a prerequisite |
| A extends/builds on B | `extends` | A is a specialization of B |
| A contrasts with B | `contrasts` | A and B are alternatives or opposites |
| A and B are related | `relates_to` | General topical connection |

Guidelines:
- Prefer specific types (`requires`, `extends`, `contrasts`) over `relates_to`
- Ask the user to confirm non-obvious connections
- Don't over-link — 2-4 connections per neuron is typical
- Bidirectional types (`contrasts`, `relates_to`) create edges both ways

## Duplicate Detection

Before adding, check if the concept already exists:

```bash
spkt retrieve "<term>" --json
```

If a near-duplicate is found:
1. Show the existing neuron to the user
2. Ask: update existing, merge, or add as separate?
3. If merging: combine content and transfer synapses

## Batch Ingestion

When the user provides multiple items at once (e.g., study notes, article
highlights), process them in a batch:

1. Split into atomic concepts
2. Show the proposed split to the user for confirmation
3. Add all neurons
4. Discover inter-batch relations (new neurons relating to each other)
5. Discover external relations (new neurons relating to existing graph)
6. Create all synapses

## Example Session

```
> /spkt-teach

What would you like to add to your brain?

> モナドは自己関手の圏におけるモノイド対象。
  bind (>>=) で計算を連鎖させる。
  HaskellではIOやMaybeが代表例。

I'll create 1 neuron from this:

── Neuron: Monad ──
# モナド (Monad)

自己関手の圏におけるモノイド対象。bind (>>=) で計算を連鎖させる。

## Examples
- IO: 副作用のある計算を純粋に記述
- Maybe: 失敗する可能性のある計算の連鎖

Type: concept | Domain: math

Found 3 related neurons:
  1. Functor (0.82) → requires
  2. Applicative (0.78) → requires
  3. Category Theory basics (0.71) → relates_to

Create with these connections? [Y/n]

✅ Added neuron n-abc123
🔗 Linked: Monad --requires--> Functor
🔗 Linked: Monad --requires--> Applicative
🔗 Linked: Monad --relates_to--> Category Theory basics
```

## Brain Discovery

The skill should discover the brain automatically. If no brain is found
in the current directory tree, ask the user which brain to use.
Use `--brain <path>` with all `spkt` commands.

## Output Format

Keep output concise. After ingestion, report a single summary line:

```
Added N neurons, M synapses. Source linked.
```

- **Neuron count**: how many created
- **Synapse count**: how many connections discovered and created
- **Source**: mention only when attached (URL or file)
- Do NOT list every neuron ID or synapse individually unless asked
- For batch ingestion, show summary then offer "Want to see details?"

When confirming before creation:
```
Will add 3 neurons (concept/math) with 4 synapses.
Source: https://example.com/article
Proceed? [Y/n]
```

## Commands Used

```bash
spkt neuron add "<content>" -t <type> -d <domain> --json                   # Add neuron
spkt neuron add "<content>" -t <type> --source-url "<url>" --json          # Add with source
spkt source learn "<url-or-path>" -d <domain> --json                       # Fetch + create Source
spkt retrieve "<query>" --json                                      # Find related
spkt synapse add <a> <b> -t <type>                                         # Create synapse
spkt neuron list --json                                                    # List existing neurons
spkt neuron inspect <id> --json                                            # Neuron detail + sources
spkt community detect --json                                    # Re-detect communities
```
