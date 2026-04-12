---
name: TEMPLATE-extractor
description: One-line description of when this extractor should be picked. Edit this whole header.
allowed-tools: Bash(spkt *), Read, Glob
---

# TEMPLATE Extractor

> Replace this whole file with the actual extractor instructions.

## When to use

Describe what kind of input this extractor handles and why it beats the
default markdown chunker for that input.

## Preprocessing

If you ship a helper script next to this SKILL.md, document how to call it:

```bash
python3 {SKILL_DIR}/extract.py <input>
```

(`{SKILL_DIR}` should be replaced with the resolved extractor path at
invocation time.)

## Neuron creation rules

How to split the preprocessed output into atomic, self-contained, titled
neurons. Be specific about the per-format conventions (e.g. "one neuron per
function definition", "one neuron per section heading").

## Synapse suggestions

After neurons are created, what relationships should be discovered?
List the synapse types you generate and how you decide on each.

## Output

```
Added N neurons, M synapses (TEMPLATE extractor).
```
