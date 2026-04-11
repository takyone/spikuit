# 実装詳細

## APPNP伝播

Personalized PageRank拡散です:

```
Z = (1 - alpha) * A_hat @ Z + alpha * H
```

- `alpha` = テレポート確率（大きいほどローカル、デフォルト: 0.15）
- `A_hat` = 自己ループ付き正規化隣接行列
- `H` = 初期活性化（グレード依存）

## STDPエッジ重み更新

`tau_stdp`日以内の共発火タイミングでエッジ重みを更新します:

- プレがポストの前（LTP）: `dw = +a_plus * exp(-|dt| / tau)`
- ポストがプレの前（LTD）: `dw = -a_minus * exp(-|dt| / tau)`

## LIF圧力モデル

圧力は近傍の発火で蓄積し、指数的に減衰します:

```
pressure(t) = pressure * exp(-dt / tau_m)
```

## `fire()`の動作

```
circuit.fire(spike)
  1. スパイクをDBに記録
  2. FSRS: 安定性、難易度を更新、次回復習をスケジュール
  3. APPNP: 近傍に活性化を伝播（圧力デルタ）
  4. ソースニューロンの圧力をリセット
  5. STDP: 共発火タイミングに基づきエッジ重みを更新
  6. 将来のSTDP用にlast-fireタイムスタンプを記録
```

## 可塑性パラメータ

| パラメータ | デフォルト | 制御対象 |
|-----------|---------|---------|
| `alpha` | 0.15 | APPNPテレポート確率（局所性） |
| `propagation_steps` | 5 | APPNP反復回数 |
| `tau_stdp` | 7.0 | STDP時間窓（日） |
| `a_plus` | 0.03 | STDP LTP振幅 |
| `a_minus` | 0.036 | STDP LTD振幅 |
| `tau_m` | 14.0 | LIF膜時定数（日） |
| `pressure_threshold` | 0.8 | LIF圧力閾値 |
| `weight_floor` | 0.05 | 最小エッジ重み |
| `weight_ceiling` | 1.0 | 最大エッジ重み |

## エンベディングパイプライン

### 入力の前処理

エンベディング前に、Neuronコンテンツは以下のパイプラインを通ります:

```
生のNeuronコンテンツ
  → YAMLフロントマターを除去
  → フロントマターから [Section: ...] を付加（あれば）
  → Sourceのsearchableメタデータから [key: value] を付加（max_searchable_charsで切り詰め）
  → 最終エンベディング入力
```

構造的なノイズ（フロントマターのキーや書式）を取り除きつつ、
本文だけでは拾えない意味的な文脈をエンベディングに反映させます。

### タスクタイププレフィックス

エンベディングモデルの多くは、入力に目的（文書 or クエリ）を明示すると
精度が上がります。`config.toml` の `prefix_style` で設定できます:

```toml
[embedder]
prefix_style = "nomic"    # "nomic", "google", "cohere", "none"
```

| スタイル | 文書プレフィックス | クエリプレフィックス |
|---------|------------------|-------------------|
| `nomic` | `search_document: ` | `search_query: ` |
| `google` | `RETRIEVAL_DOCUMENT: ` | `RETRIEVAL_QUERY: ` |
| `cohere` | `search_document: ` | `search_query: ` |
| `none`（デフォルト） | — | — |

プレフィックスは自動で適用されます:
- `EmbeddingType.DOCUMENT` — Neuronの追加・更新、`embed-all` 実行時
- `EmbeddingType.QUERY` — `retrieve()` 呼び出し時

### searchableメタデータの結合式

Sourceにsearchableメタデータがある場合、エンベディング入力は:

```
[key1: value1] [key2: value2] [Section: section_name] 本文テキスト
```

`max_searchable_chars`（デフォルト: 500）を超える分は切り詰められ、
メタデータがエンベディングを支配しないようになっています。

## エンベッダープロバイダー

| プロバイダー | API | 用途 |
|------------|-----|------|
| `openai-compat` | `/v1/embeddings` | LM Studio, Ollama /v1, vLLM, OpenAI |
| `ollama` | `/api/embed` | Ollama ネイティブAPI |
| `none` | — | エンベディングなし（キーワード検索のみ） |

## ニューロンモデルのマッピング

| 脳 | Spikuit | 役割 |
|----|---------|------|
| ニューロン | `Neuron` | 知識の単位（Markdown） |
| シナプス | `Synapse` | 型付き・重み付きの接続 |
| スパイク | `Spike` | 復習イベント（活動電位） |
| 回路 | `Circuit` | ナレッジグラフ全体 |
| 可塑性 | `Plasticity` | チューニング可能な学習パラメータ |

## 技術スタック

| コンポーネント | 技術 |
|-------------|------|
| モデル | msgspec.Struct |
| ストレージ | SQLite (aiosqlite) + NetworkX + sqlite-vec |
| スケジューリング | FSRS v6 |
| エンベディング | httpx (OpenAI-compat / Ollama) |
| CLI | Typer |
| 可視化 | pyvis (vis.js) |
| 言語 | Python 3.11+ |
