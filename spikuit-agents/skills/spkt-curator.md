# /spkt-curator — Brain Curator Session

Maintain and improve your knowledge graph through conversation. Diagnose
domain misalignment, clean up labels, resolve orphans, and run consolidation.

## Prerequisites

- A Brain must be initialized (`spkt init`)
- The `spkt` CLI must be available
- Communities should be detected (`spkt community detect`) for domain audit

## Session Flow

1. **Diagnose**: Run `spkt domain audit --json` and `spkt diagnose --json`
2. **Present**: Summarize findings conversationally — prioritize actionable items
3. **Walk through**: Address each suggestion one at a time with user approval
4. **Execute**: Apply approved changes
5. **Summarize**: Report what was done

## Diagnostic Commands

```bash
spkt domain audit --json              # Domain ↔ community alignment
spkt diagnose --json                  # Brain health (orphans, weak synapses, stale)
spkt progress --json                  # Learning progress & retention
spkt consolidate --json               # Consolidation dry-run (synapse decay/prune)
```

## Curation Actions

### Domain Cleanup

**Split** (domain spans multiple communities):
- `spkt domain audit --json` identifies the split
- Show neurons in each community cluster
- Rename a subset: `spkt domain rename <old> <new-sub>`

**Merge** (multiple domains in one community):
- `spkt domain merge <d1> <d2> --into <target>`
- Use keyword hints from audit to suggest the best name

**Rename**:
- `spkt domain rename <old> <new>`

### Orphan Resolution

When `diagnose` finds neurons with no synapses:
- Search for related: `spkt retrieve "<content>" --json`
- Connect: `spkt synapse add <orphan> <related> -t relates_to`
- Or remove if no value: `spkt neuron remove <id>`

### Weak Synapse Review

When `diagnose` finds synapses with weight < 0.3:
- Inspect both ends: `spkt neuron inspect <id> --json`
- Strengthen if valid: `spkt synapse weight <a> <b> 0.6`
- Remove if spurious: `spkt synapse remove <a> <b>`

### Duplicate Merging

- Search: `spkt retrieve "<term>" --json`
- Merge: `spkt neuron merge <dup1> <dup2> --into <keeper>`

### Consolidation

- Preview: `spkt consolidate --json`
- Apply after approval: `spkt consolidate apply --json`

## Conversation Style

- Start with the highest-impact finding, not a wall of diagnostics
- Present one category at a time (domains → orphans → weak synapses → consolidation)
- For each suggestion: explain what and why, then ask for approval
- After each action, confirm success briefly
- Let the user steer — they may want to focus on one area

## Decision Framework

| Situation | Suggestion |
|-----------|-----------|
| Domain spans 2+ communities | Split into sub-domains using keyword hints |
| Multiple domains in 1 community | Merge, use most descriptive name |
| Orphan with related content nearby | Connect with appropriate synapse type |
| Orphan with no related content | Ask user: keep or remove? |
| Weak synapse between related concepts | Strengthen to 0.5-0.7 |
| Weak synapse between unrelated concepts | Remove |
| Stale neuron (never reviewed, old) | Ask: still relevant? |
| Dangling prerequisite | Find or create the missing concept |

## Output Format

Keep summaries concise:
```
Curated: 2 domains merged, 3 orphans connected, 1 weak synapse removed.
```

When asking for approval, be specific:
```
Domain "ml" spans 2 communities:
  c0: supervised learning, regression, classification (12 neurons)
  c3: reinforcement learning, Q-learning, policy gradient (8 neurons)

Split into "ml-supervised" and "ml-reinforcement"? [Y/n]
```

## Commands Used

```bash
spkt domain audit --json
spkt diagnose --json
spkt progress --json
spkt consolidate --json
spkt consolidate apply --json

spkt domain list --json
spkt domain rename <old> <new>
spkt domain merge <d1> <d2> --into <target>

spkt neuron list -d <domain> --json
spkt neuron inspect <id> --json
spkt neuron remove <id> --json
spkt neuron merge <id1> <id2> --into <target> --json

spkt synapse add <a> <b> -t <type>
spkt synapse weight <a> <b> <weight>
spkt synapse remove <a> <b>
spkt synapse list --neuron <id> --json

spkt retrieve "<query>" --json
spkt community detect --json
spkt community list --json
```
