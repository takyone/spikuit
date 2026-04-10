# コンセプト

## アーキテクチャ

```
spikuit/
├── spikuit-core/          # LLM非依存エンジン
│   ├── models.py          #   Neuron, Synapse, Spike, Plasticity, Scaffold
│   ├── circuit.py         #   公開API: fire, retrieve, ensemble, due
│   ├── propagation.py     #   APPNP拡散 + STDP + LIF減衰
│   ├── db.py              #   非同期SQLite + sqlite-vec 永続化
│   ├── embedder.py        #   差し替え可能な埋め込みプロバイダー
│   ├── session.py         #   セッション抽象化（QABot、Learn）
│   ├── scaffold.py        #   ZPD着想のスキャフォールディング
│   ├── learn.py           #   学習プロトコル（Flashcard、拡張可能）
│   └── config.py          #   .spikuit/ Brain設定と探索
├── spikuit-cli/           # spkt コマンド (Typer)
└── spikuit-agents/        # エージェントアダプター（予定）
```

## アルゴリズム

### FSRS (Free Spaced Repetition Scheduler)

ニューロン単位の間隔反復。各ニューロンはFSRS Cardを持ち、stability（安定度）、
difficulty（難易度）、次回復習日を追跡します。伝播はFSRS状態に**一切触れません**
-- 影響するのは圧力（pressure）だけです。

### APPNP (Approximate Personalized Propagation of Neural Predictions)

スパイクを発火すると、Personalized PageRankを通じて近傍に活性化が伝播します。
これが関連概念に**復習圧力**を生み出し、次に何を学ぶべきかを示唆します。

```
Z = (1 - alpha) * A_hat @ Z + alpha * H
```

- `alpha` = テレポート確率（高いほどローカル）
- `A_hat` = 自己ループ付き正規化隣接行列
- `H` = 初期活性化（グレードに依存した強度）

### STDP (Spike-Timing-Dependent Plasticity)

`tau_stdp`日以内の共発火タイミングに基づいてエッジ重みが更新されます:

- **Preが先に発火（LTP）**: `dw = +a_plus * exp(-|dt| / tau)`
- **Postが先に発火（LTD）**: `dw = -a_minus * exp(-|dt| / tau)`

関連概念を一緒に復習すると接続が強化され、しないと弱まります。

### LIF (Leaky Integrate-and-Fire)

復習圧力は近傍の発火から蓄積し、指数関数的に減衰します:

```
pressure(t) = pressure * exp(-dt / tau_m)
```

圧力が閾値を超えると、ニューロンは自発的復習の「準備ができた」状態になります。

## セッション

セッションはBrain（Circuit）のインタラクションモードです。
Brainは共通のバックエンド、セッションがインタラクション方法を定義します。

### QABotSession

自己最適化するRAGチャット:

- **ネガティブフィードバック**: 類似フォローアップクエリが前回結果をペナルティ
- **Accept**: 明示的な正のフィードバックでニューロンをブースト
- **重複排除**: 既に返されたニューロンを除外
- **永続/一時**: ブーストのコミット有無を選択可能

### LearnSession

会話型ナレッジキュレーション:

- **ingest**: ニューロンを追加し、関連概念を自動発見
- **relate**: シナプスを作成または強化
- **search**: グラフ重み付き検索
- **merge**: 重複ニューロンを統合（シナプス転送 + コンテンツ結合）

### 会話型RAGキュレーション

核心的な洞察: **会話が直接検索品質を改善する**。

従来のRAGはナレッジベースを静的に扱います。Spikuitのグラフは生きています
-- 復習、検索結果の受諾、キュレーション操作のすべてが構造を改善します。
結果として、**使うほど良くなる**RAGシステムが生まれます。

## Embedder

差し替え可能なテキスト埋め込み（複数プロバイダー対応）:

| プロバイダー | API | ユースケース |
|-------------|-----|-------------|
| `openai-compat` | `/v1/embeddings` | LM Studio, Ollama /v1, vLLM, OpenAI |
| `ollama` | `/api/embed` | Ollamaネイティブ API |
| `none` | -- | 埋め込みなし（キーワード検索のみ） |

埋め込みはsqlite-vecにKNN検索用に保存され、retrieveのスコアリングで使用されます:

```
score = max(キーワード類似度, 意味的類似度) * (1 + 検索可能性 + 中心性 + 圧力 + ブースト)
```

## Scaffold

ZPD（発達の最近接領域）着想のサポートレベル。
FSRS状態とグラフ近傍から算出:

| レベル | 条件 | 内容 |
|--------|------|------|
| **FULL** | 新規 / Learning状態 | 最大ヒント、フルコンテンツ、易しい問題 |
| **GUIDED** | Relearning / 低stability | リクエスト時ヒント、部分コンテンツ |
| **MINIMAL** | Review + 中程度のstability | 難しい問題、タイトルのみ |
| **NONE** | 高stability（習得済み） | 純粋な想起、応用レベル |

Scaffoldはさらに以下を特定します:

- **Context**: 強い近傍（学習者がよく知っているスキャフォールディング素材）
- **Gaps**: 弱い前提条件（先に学習すべきもの）

## Learnプロトコル

抽象プロトコル: select -> scaffold -> present -> evaluate -> record

- **Flashcard**: セルフグレードのフラッシュカード（LLM不要）。
  Scaffoldレベルがコンテンツの表示量を制御。
- **Quiz**（agents経由）: LLM生成の問題、ニューロン単位のグレーディング。

## 技術スタック

| コンポーネント | 技術 |
|---------------|------|
| モデル | msgspec.Struct |
| ストレージ | SQLite (aiosqlite) + NetworkX + sqlite-vec |
| スケジューリング | FSRS v6 |
| 埋め込み | httpx (OpenAI互換 / Ollama) |
| CLI | Typer |
| 可視化 | pyvis (vis.js) |
| 言語 | Python 3.11+ |
