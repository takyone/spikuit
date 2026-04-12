# コンセプト

## Brain

**Brain**はひとまとまりのナレッジ空間です —
[Obsidianのvault](https://obsidian.md/)やgitリポジトリに近い考え方です。
`.spikuit/`ディレクトリの中に、ナレッジグラフ・設定・復習スケジュールが
すべて収まっています。

```
my-project/
└── .spikuit/
    ├── config.toml    # Brain設定（名前、エンベッダー）
    ├── circuit.db     # SQLiteデータベース
    └── cache/         # エンベディングキャッシュ
```

### 複数のBrain

分野やプロジェクトごとに、好きなだけBrainを作れます。

```bash
~/math/.spikuit/      # 圏論、代数
~/french/.spikuit/    # フランス語の語彙と文法
~/work/.spikuit/      # 仕事関連の知識
```

### 自動検出

gitと同じく、`spkt`はカレントディレクトリから親を辿って`.spikuit/`を見つけます。
別のBrainを操作したいときは`--brain <path>`で指定します。

## ナレッジグラフ

Spikuitでは知識を**グラフ**で整理します。概念がノード、関係がエッジです。

### Neuron

**Neuron**は知識の最小単位で、Markdownで保存されます。
type（concept、term、procedureなど）と
domain（math、french、csなど）を持てます。

```bash
spkt neuron add "# Functor\n\n圏の間の構造を保つ写像。" -t concept -d math
```

### Synapse

**Synapse**は2つのNeuronをつなぐ型付きの接続です。

| タイプ | 方向 | 意味 |
|-------|------|------|
| `requires` | A → B | AにはBの理解が必要 |
| `extends` | A → B | AはBを拡張 |
| `contrasts` | A ↔ B | AとBは対比関係 |
| `relates_to` | A ↔ B | 一般的な関連 |
| `summarizes` | A → B | コミュニティ要約 → メンバー |

接続には重みがあり、使い方次第で**強くも弱くもなります**。
関連する概念を近い時期に復習すれば、そのつながりは強まります。

### Source

**Source**は知識の出どころ（URL、論文、書籍、ファイル）を追跡します。
回答時の引用やバージョン追跡に使えます。

```bash
spkt neuron add "# 重要な発見" --source-url "https://paper.com" --source-title "論文"
spkt source ingest "https://paper.com" -d cs --json    # URL取り込み
spkt source ingest ./papers/ -d cs --json              # ディレクトリ一括取り込み
```

1つのSourceから複数のNeuronが生まれることもあれば（1:N）、
複数のNeuronが同じSourceを共有することもあります（M:N）。URLで自動的に重複排除されます。

#### メタデータの2層構造

Sourceには2種類のメタデータを持たせられます:

| レイヤー | 役割 | 使われ方 |
|---------|------|---------|
| **filterable** | 絞り込み用の構造化データ | SQL WHERE相当 — キーが無いSourceは結果から外れる |
| **searchable** | 関連度を上げるフリーテキスト | エンベディング入力に合成 — 意味検索の精度向上 |

```jsonl
{"file_name": "paper.md", "filterable": {"year": "2024", "venue": "NeurIPS"}, "searchable": {"abstract": "We propose..."}}
```

filterableは厳密なフィルタです。`--filter year=2024` は `year`キーを持ち
値が`2024`のSourceだけを返します。キーが存在しないSourceは除外されます。

searchableは柔らかいシグナルです。Neuronの本文の前に付加してから
エンベディングするため、メタデータの意味もベクトルに反映されます。

#### ソースの鮮度管理

URLソースは最終取得日時を記録しており、古くなったものを検出できます:

```bash
spkt source refresh --stale 30           # 30日以上更新していないSourceを再取得
spkt source refresh <source-id>          # 指定したSourceを再取得
```

条件付きGET（ETag / Last-Modified）で帯域を節約しつつ、
内容が変わっていれば関連Neuronを自動で再エンベディングします。
404を返すSourceは `unreachable` としてマークされます。

### コミュニティ

Spikuitは**コミュニティ** — 密につながったNeuronの塊 — を
Louvainアルゴリズムで自動検出します。検索時にトップヒットと同じクラスタの結果を
優先的に返すため、検索の質が上がります。

```bash
spkt community detect                      # コミュニティを検出
spkt community detect --summarize          # 要約Neuronも自動生成
spkt community list --json                 # 現在の割り当てを表示
```

可視化でもコミュニティごとにノードが色分けされるため、
知識のまとまりが一目で分かります。

### 統合（Consolidation）

ナレッジグラフは使い続けるうちに弱い接続や使われないSynapseが溜まってきます。
Spikuitでは**睡眠中の記憶統合**にヒントを得た仕組みで、グラフを整理できます:

- **SHY（シナプスホメオスタシス）**: 弱い接続の重みを一律に下げる
- **SWS（徐波睡眠）**: 閾値を下回った接続を剪定
- **REM**: 統合の機会を検出（計画中）

```bash
spkt consolidate              # まずドライラン — 何が起きるか確認
spkt consolidate apply        # 確認できたら適用
```

### なぜグラフなのか？

フラッシュカードは1枚1枚が独立しています。でも知識は独立していません
— 「モナド」を理解するには、まず「ファンクター」を知る必要がある。
グラフならこの依存関係を自然に表現できて、次のようなことが可能になります:

- **前提知識の検出** — 何から学ぶべきかが分かる
- **活性化の伝播** — 1つ復習すると、関連する知識にも波及
- **構造を考慮した検索** — テキストの類似度だけでなく、グラフの構造もランキングに反映

## 間隔反復

各Neuronは[FSRS](https://github.com/open-spaced-repetition/fsrs4anki)による
独自の復習スケジュールを持ちます — 最新のAnkiと同じアルゴリズムです。

| Grade | 意味 |
|-------|------|
| `miss` | 思い出せなかった |
| `weak` | 曖昧 |
| `fire` | 正解 |
| `strong` | 完璧に想起 |

復習すると2つのことが起きます:

1. **スケジュールが更新される** — 正解なら安定性が上がり、不正解なら下がる
2. **関連Neuronにも影響が及ぶ** — 「Functor」を復習すると「Monad」の
   復習タイミングが少しだけ早まる

つまり復習キューは個々のNeuronの期日だけでなく、
知識全体の*つながり*に影響されます。

## 検索

Spikuitの検索は複数のシグナルを掛け合わせます:

```
スコア = テキスト類似度 × (1 + 記憶の強さ + 中心性 + 圧力 + フィードバック + コミュニティブースト)
```

- **テキスト類似度**: キーワード + セマンティック（エンベディング）
- **記憶の強さ**: よく定着している知識ほど上位に
- **中心性**: 多くの知識とつながっている概念ほど上位に
- **圧力**: 最近の復習で「プライミング」された概念が上位に
- **フィードバック**: 過去の検索で採用/不採用した履歴がランキングに反映
- **コミュニティブースト**: トップヒットと同じクラスタの結果を優遇

同じクエリでも、知識の蓄積や使い方の変化に応じて返る結果が変わります。

## スキャフォールディング

Neuronごとの理解度に応じて、出題の仕方を変えます:

| レベル | タイミング | 内容 |
|-------|----------|------|
| Full | 初見の概念 | サポート最大 — フルコンテキスト表示、やさしい問題 |
| Guided | 学習途中 | ヒント付き、適度な難易度 |
| Minimal | だいぶ定着 | サポート控えめ — 骨のある問題 |
| None | 習得済み | 記憶だけで答える — 応用問題 |

まだ習得していない前提知識（**ギャップ**）も検出し、
「先にこっちを復習したほうがいい」と提案します。

## セッション

Brainを使ったLLM連携の対話モードです:

| セッション | できること |
|-----------|----------|
| **QABotSession** | RAGチャット — 知識ベースに聞いて、ソース付きで回答。使うほど検索精度が向上。 |
| **IngestSession** | 会話で知識を追加 — 関連概念の自動発見、重複チェック付き。 |
| **TutorSession** | AIチューター — 弱点を見つけて教え、クイズし、フィードバックまで。 |

セッションは**永続**（フィードバックを次回以降に活かす）と
**一時**（その場限りで捨てる）を選べます。

## エクスポートとデプロイ

### QABotバンドル

**QABotバンドル**は検索に必要な最小限だけを詰めたポータブルなSQLiteです。
Neuron・Synapse・エンベディング・出典情報が入っています。

```bash
spkt export --format qabot -o qa-bundle.db
```

FSRSの状態・復習履歴・生ソースファイルは含まれません。
知識と検索用ベクトルだけの軽量パッケージです。

`Circuit(read_only=True)` で読み込めます:

```python
circuit = Circuit(db_path="qa-bundle.db", read_only=True)
results = await circuit.retrieve("query")  # 検索はできる
await circuit.add_neuron(...)              # ReadOnlyError
```

用途: サーバーにQABotをデプロイ、復習データ抜きでBrainを共有、
静的なRAGエンドポイントの構築。

### その他のフォーマット

| フォーマット | コマンド | 用途 |
|------------|---------|------|
| tarball | `spkt export -o backup.tar.gz` | フルバックアップ |
| JSON | `spkt export --format json -o brain.json` | 共有・検査 |

## アーキテクチャ

```
spikuit-core/     # 純粋なエンジン（LLM依存なし）
├── Circuit       #   ナレッジグラフ + FSRS + 伝播
├── Embedder      #   プラガブルなエンベディング（タスクタイププレフィックス対応）
├── Sessions      #   QABot, Ingest, Tutor
└── Quiz          #   クイズ戦略（Flashcard, AutoQuiz）

spikuit-cli/      # spktコマンド（Typer）
spikuit-agents/   # エージェントスキルとアダプター
```

コアエンジンは**LLMなしで完結**します。すべての`spkt`コマンドはLLM不要です。
セッションやスキルが、その上にLLMを活用した対話レイヤーを足す形です。

アルゴリズムの詳細（FSRS、グラフ伝播、スコアリング、エンベディング）は
[Appendix: アルゴリズム](appendix/index.md)を参照してください。
