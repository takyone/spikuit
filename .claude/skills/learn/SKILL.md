---
name: learn
description: "Add new knowledge to the circuit from the current conversation. Use when the user says /learn, 'learn this', 'add this to spikuit', '覚えて', 'ナレッジに追加', '知識追加', or similar."
---

# Learn — Add Knowledge to Circuit

Extract knowledge from the conversation and add it as Neurons with Synapses.

## Steps

### 1. Identify what to add

From the current conversation, identify discrete pieces of knowledge worth remembering. Each should become one Neuron.

Guidelines:
- One concept per Neuron (atomic knowledge)
- Content should be self-contained Markdown
- Include a `# Title` heading
- Add explanation, examples, or key points in the body
- Determine appropriate `type` and `domain`

Common types: `concept`, `theorem`, `definition`, `example`, `procedure`, `vocabulary`
Common domains: `math`, `cs`, `language`, `philosophy`, `economics`

### 2. Add neurons

For each piece of knowledge:

```bash
spkt add "<markdown content>" --type <type> --domain <domain> --json
```

If the knowledge comes from a specific source (URL, paper, etc.), attach it:

```bash
spkt add "<content>" --type <type> --domain <domain> --source-url "<url>" --source-title "<title>" --json
```

For bulk ingestion from a URL or file:

```bash
spkt learn "<url-or-path>" -d <domain> --json   # fetches content + creates Source
# then chunk the returned content into neurons with --source-url
```

Note: Use `\n` for newlines in the content string.

Save the returned neuron IDs.

### 3. Find related existing neurons

For each new neuron, search for related existing knowledge:

```bash
spkt retrieve "<relevant keywords>" --json
```

### 4. Create synapses

If related neurons exist, create appropriate connections:

```bash
spkt link <new_id> <existing_id> --type <synapse_type> --json
```

Choose the synapse type based on the relationship:
- `requires` — New concept requires understanding the existing one
- `extends` — New concept extends or builds on the existing one
- `contrasts` — Concepts are in contrast or opposition
- `relates_to` — General association (default)

### 5. Confirm to user

Show what was added:
- List of new Neurons (title + ID)
- Synapses created
- Suggest running `/review` to reinforce the new knowledge

## Notes

- Always use `--json` for spkt commands
- If the user provides content in a specific language, keep the Neuron content in that language
- Don't over-link — only create synapses for meaningful relationships
- Respond in the user's language
