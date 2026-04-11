# /spkt-qabot — RAG Chat Session

Query your brain with natural language. Retrieval improves as you chat.

## Prerequisites

- A Brain must be initialized with embeddings (`spkt init` with a provider)
- The `spkt` CLI must be available

## Session Flow

1. **Start session**: Initialize QABotSession (persistent or ephemeral)
2. **User asks a question**: Free-form natural language query
3. **Retrieve**: `spkt retrieve "<query>" --json` to find relevant neurons
4. **Generate answer**: Synthesize an answer from retrieved neurons
5. **Present**: Show the answer with source neuron references
6. **Feedback loop**: User can accept, follow up, or change topic
7. **Close**: Commit retrieval boosts (if persistent)

## Answer Generation

When generating an answer from retrieved neurons:

- **Synthesize, don't copy**: Combine information from multiple neurons
- **Cite sources**: Reference neuron IDs so the user can inspect them
- **Acknowledge gaps**: If retrieval doesn't cover the question, say so
- **Match language**: Answer in the same language as the question

### Answer Format

Use source URLs from `spkt neuron inspect --json` (the `sources` array) for proper citation.
When sources are available, cite with URL. Otherwise, cite by neuron ID.

```
[Answer synthesized from retrieved neurons]

Sources:
- [Source Title](https://example.com/paper.pdf) (via n-abc123)
- n-def456: Neuron title (no source URL)
```

## Feedback Loop

The QABotSession self-optimizes retrieval through implicit and explicit feedback:

### Implicit Negative Feedback
When the user asks a similar follow-up question, the session interprets this
as "prior results weren't good enough" and penalizes previously returned neurons.
This happens automatically — no action needed from the skill.

### Explicit Positive Feedback (Accept)
When the user indicates an answer was helpful ("good", "thanks", "that's right"),
mark the returned neurons as accepted. This boosts their retrieval weight.

### Topic Change (Reset)
When the user changes topic, reset the session to clear prior query context.
Detect topic changes by comparing the new query to prior queries — if similarity
is low, it's a new topic.

## Persistent vs Ephemeral

| Mode | When to use | Behavior |
|------|------------|----------|
| Persistent (default) | Building long-term retrieval quality | Boosts committed to DB on close |
| Ephemeral | One-off exploration, testing | Boosts discarded on close |

Ask the user which mode if unclear, default to persistent.

## Context Expansion

For each retrieved neuron, also fetch its neighbors (ensemble) to provide
richer context:

```bash
spkt neuron inspect <id> --json  # Includes neighbor IDs
```

Use neighbor content to:
- Provide prerequisite context (via `requires` synapses)
- Mention related concepts (via `relates_to` synapses)
- Note contrasts (via `contrasts` synapses)

## Multi-turn Conversations

Track conversation state across turns:

1. **Deduplication**: Don't return the same neuron twice in a session
2. **Context accumulation**: Prior answers inform follow-up interpretation
3. **Progressive depth**: As the user asks more, draw from deeper graph connections

## Example Session

```
> /spkt-qabot

QABot session started (persistent mode).
Ask me anything about your brain.

> APPNPってどういうアルゴリズム？

APPNPはPersonalized PageRankをグラフニューラルネットワークに適用した手法です。
標準的なGCNと異なり、テレポート確率αで局所性を制御し、ノードごとに異なる
初期シグナル（H）を使います。これにより、遠くのノードからも情報を集約
しつつ、元のノード特徴を保持できます。

GCNが層を重ねるとover-smoothingが起きるのに対し、APPNPは
Personalized PageRankの収束性を利用して、深い伝播でも安定します。

Sources:
- n-abc123: APPNP
- n-def456: PageRank
- n-ghi789: GCN over-smoothing

> GCNとの違いをもう少し詳しく

[Session automatically penalizes prior results, retrieves new neurons]

APPNPとGCNの主な違いは伝播メカニズムにあります：

1. **伝播の深さ**: GCNは層数=伝播ステップ。APPNPは任意のKステップ伝播を
   パラメータ増加なしで実行可能
2. **Over-smoothing**: GCN は 2-3層が限界。APPNP はテレポートで回避
3. **計算グラフ**: GCNは各層で変換+伝播。APPNPは変換(MLP)と伝播(PPR)を分離

Sources:
- n-jkl012: GCN architecture
- n-mno345: Over-smoothing in deep GNNs

> いいね、ありがとう

✅ Accepted: n-abc123, n-def456, n-jkl012, n-mno345
   (retrieval boost applied)
```

## Brain Discovery

The skill should discover the brain automatically. If no brain is found
in the current directory tree, ask the user which brain to use.
Use `--brain <path>` with all `spkt` commands.

## Output Format

Structure every answer consistently:

```
[Synthesized answer in the user's language]

Sources:
- [Title](url) (via n-abc123)
- n-def456: Neuron title
```

- **Answer first, sources last** — never lead with retrieval internals
- **Cite with URL** when Source metadata is available; fall back to neuron ID
- **No retrieval internals** — don't mention scores, community IDs, or boost mechanics
- On accept feedback, confirm briefly: `Retrieval boost applied.`

## Commands Used

```bash
spkt retrieve "<query>" --brain <path> --json  # Semantic search
spkt neuron inspect <id> --brain <path> --json        # Neuron detail + neighbors + sources
spkt community list --json                        # View community structure
```
