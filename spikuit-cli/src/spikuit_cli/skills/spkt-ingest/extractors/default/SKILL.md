---
name: default-extractor
description: Generic markdown ingestion. Splits input into atomic, self-contained, titled neurons. Used as the fallback when no specialized extractor matches.
allowed-tools: Bash(spkt *), Read, Glob
---

# Default Extractor

The fallback ingestion strategy used by `spkt-ingest` whenever no
specialized extractor matches the input.

## When to use

- Free-form text or markdown the user pastes into the conversation
- Markdown files with no structure beyond headings
- URLs that have already been fetched into a single blob of text
- Anything that does not match a more specialized extractor's `[match]` rules

## Preprocessing

None — work directly with the source text.

## Neuron creation rules

1. **One concept per neuron.** Multi-concept input must be split.
2. **Self-contained.** A neuron must be readable without external context.
3. **Titled.** Start every neuron with `# Term` or `# Concept Name`.

| Input shape | How to split |
|---|---|
| Definition | One neuron: `# Term\n\nDefinition.` |
| Comparison of A vs B | Two neurons + one `contrasts` synapse |
| Multi-step process | One neuron for the process, optional sub-neurons per step |
| Long article | One neuron per H2/H3 section, with `requires` for prerequisites |

## Synapse suggestions

After all neurons are created:

1. For each new neuron, run `spkt retrieve "<first 200 chars>" --json`
2. Inspect the top 3-5 hits and propose synapses:
   - `requires` if the new neuron's understanding depends on the hit
   - `extends` if the new neuron builds on the hit
   - `contrasts` if they are compared / opposed
   - `relates_to` for general association (last resort)
3. Aim for 2-4 synapses per neuron.

## Output

Report a single summary line:

```
Added N neurons, M synapses (default extractor).
```
