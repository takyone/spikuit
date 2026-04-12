# CLIリファレンス

すべてのコマンドで `--json` フラグが使えます。

## グローバルオプション

ほぼ全コマンド共通のフラグ:

| オプション | 説明 |
|-----------|------|
| `--brain`, `-b` | Brainルートディレクトリ（自動探索を上書き） |
| `--json` | マシンリーダブルなJSON出力 |

## Brain管理

### `spkt init`

カレントディレクトリに新しいBrainを作成します。
フラグなしなら対話ウィザードが立ち上がります。
`--json` や `--provider` を指定すれば非対話で実行できます。

```
$ spkt init

Brain name [my-project]:
Configure embeddings? [y/N]: y
  Providers: openai-compat, ollama
  Provider [openai-compat]:
  Base URL [http://localhost:1234/v1]:
  Model [text-embedding-nomic-embed-text-v1.5]:
  Dimension [768]:

--- Summary ---
...
Create brain? [Y/n]:
```

非対話（スクリプト・エージェント向け）:

```bash
spkt init -p none                      # 埋め込みなし
spkt init --name my-brain -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5
spkt init -p ollama --json             # エージェント向けJSON出力
```

### `spkt config`

いまのBrain設定を表示します。

```bash
spkt config
spkt config --json
```

### `spkt embed-all`

エンベディング未生成のNeuronをまとめて処理します。
実行前にNeuron数と推定トークン数が表示され、確認を求められます。

```bash
spkt embed-all              # 対話式 — 実行計画を表示して確認
spkt embed-all --yes        # 確認をスキップ
```

## Neuronコマンド

### `spkt neuron add`

Neuronを追加します。

```bash
spkt neuron add "# Functor\n\n圏の間の写像。" -t concept -d math
spkt neuron add "内容" --type fact --domain physics
spkt neuron add "内容" -t concept --source-url "https://example.com/paper.pdf" --source-title "論文"
```

| オプション | 説明 |
|-----------|------|
| `-t`, `--type` | Neuronタイプ（例: `concept`, `fact`, `procedure`） |
| `-d`, `--domain` | 知識ドメイン（例: `math`, `french`） |
| `--source-url` | 出典URL（引用追跡用） |
| `--source-title` | 出典タイトル（`--source-url`と併用） |

### `spkt neuron list`

Neuronの一覧。フィルタやメタデータ探索にも対応。

```bash
spkt neuron list
spkt neuron list -t concept -d math
spkt neuron list --limit 50

# メタデータ探索
spkt neuron list --meta-keys --json          # 全Sourceのfilterable/searchableキー一覧
spkt neuron list --meta-values year --json   # キーの値一覧（件数付き）
```

| オプション | 説明 |
|-----------|------|
| `-t`, `--type` | タイプでフィルタ |
| `-d`, `--domain` | ドメインでフィルタ |
| `--limit` | 最大件数 |
| `--meta-keys` | メタデータキー一覧（filterable + searchable） |
| `--meta-values KEY` | 指定キーの値一覧 |

### `spkt neuron inspect`

Neuronの詳細を表示します。コンテンツ、FSRS状態、圧力、出典、コミュニティ、接続中のSynapseが確認できます。

```bash
spkt neuron inspect <neuron-id>
spkt neuron inspect <neuron-id> --json    # sources[]とcommunity_idを含む
```

### `spkt neuron remove`

Neuronとそのすべてのシナプスを削除します。

```bash
spkt neuron remove <neuron-id>
spkt neuron remove <neuron-id> --json
```

### `spkt neuron merge`

複数のNeuronを1つにまとめます。コンテンツは結合、Synapseはターゲットに
付け替え、Source紐付けも移管。統合後にターゲットを再エンベディングします。

```bash
spkt neuron merge <source-id-1> <source-id-2> --into <target-id>
spkt neuron merge <id1> <id2> <id3> --into <target-id> --json
```

### `spkt neuron due`

復習が必要なNeuronを表示します。自動生成Neuron
（`_meta`ドメイン・`community_summary`タイプ）は対象外です。

```bash
spkt neuron due
spkt neuron due -n 20
spkt neuron due --json
```

### `spkt neuron fire`

復習を記録します（スパイクの発火）。自動生成Neuronには使えません。

```bash
spkt neuron fire <neuron-id> --grade fire
spkt neuron fire <neuron-id> -g strong
```

| グレード | 意味 | FSRS Rating |
|---------|------|-------------|
| `miss` | 失火（不正解） | Again |
| `weak` | 弱発火（怪しい） | Hard |
| `fire` | 発火（正解） | Good |
| `strong` | 強発火（完璧） | Easy |

## Synapseコマンド

### `spkt synapse add`

2つのNeuron間にSynapseを作成します。

```bash
spkt synapse add <pre-id> <post-id> --type requires
spkt synapse add <a-id> <b-id> --type relates_to
```

| タイプ | 方向 | 用途 |
|--------|------|------|
| `requires` | 片方向 | Aを理解するにはBが必要 |
| `extends` | 片方向 | AはBを拡張する |
| `contrasts` | 双方向 | AとBは対比関係 |
| `relates_to` | 双方向 | 一般的な関連 |
| `summarizes` | 片方向 | コミュニティ要約 → メンバー |

### `spkt synapse list`

Synapseの一覧。

```bash
spkt synapse list
spkt synapse list --neuron <neuron-id>     # 特定のNeuronに接続するシナプス
spkt synapse list --type requires          # タイプでフィルタ
spkt synapse list --json
```

信頼度タグ（`[inferred]`, `[ambiguous]`）があれば併記されます。

### `spkt synapse weight`

既存Synapseの重みを変更します。

```bash
spkt synapse weight <pre-id> <post-id> 0.8
spkt synapse weight <pre-id> <post-id> 0.5 --json
```

### `spkt synapse remove`

2つのNeuron間のSynapseを削除します。

```bash
spkt synapse remove <pre-id> <post-id>
spkt synapse remove <pre-id> <post-id> --json
```

## Sourceコマンド

### `spkt source ingest`

URL・ファイル・ディレクトリを取り込みます。Sourceレコードを作成し、
抽出したコンテンツをエージェントによるチャンキングに渡します。

```bash
# URL
spkt source ingest "https://example.com/article" -d cs --json

# ファイル
spkt source ingest ./notes.md -d math --json

# ディレクトリ（一括取り込み）
spkt source ingest ./papers/ -d cs --json
```

| オプション | 説明 |
|-----------|------|
| `-d`, `--domain` | ドメインタグ |
| `--title` | ソースタイトルを上書き（単一ファイル/URLのみ） |
| `--force` | searchableメタデータのサイズ超過時、切り詰めて続行 |

**ディレクトリ取り込み**はテキストファイル（`.md`, `.txt`, `.rst`, `.html`など）を
一括処理します。`metadata.jsonl`を置くとメタデータを付与できます:

```jsonl
{"file_name": "paper1.md", "title": "Paper One", "filterable": {"year": "2024", "venue": "NeurIPS"}, "searchable": {"abstract": "We propose..."}}
{"file_name": "paper2.md", "filterable": {"year": "2023"}}
```

searchableが`max_searchable_chars`（デフォルト: 500）を超えるファイルがあると
中断します。`--force` で切り詰めて続行できます。

### `spkt source list`

全Sourceの一覧（Neuron数付き）。

```bash
spkt source list
spkt source list --json
```

### `spkt source inspect`

Sourceの詳細と紐づくNeuronを表示します。

```bash
spkt source inspect <source-id>
spkt source inspect <source-id> --json
```

### `spkt source update`

Sourceのメタデータ（URL、タイトル、著者）を更新します。

```bash
spkt source update <source-id> --url "https://new-url.com"
spkt source update <source-id> --title "新しいタイトル" --author "著者名"
```

### `spkt source refresh`

URLソースを再取得して変更がないかチェックします。条件付きGET（ETag / Last-Modified）で
帯域を節約しつつ、内容が変わっていれば関連Neuronを再エンベディングします。

```bash
spkt source refresh <source-id>          # 特定のSourceを更新
spkt source refresh --stale 30           # 30日以上未取得のSourceを更新
spkt source refresh --all                # 全URLソースを更新
```

404を返すSourceは `unreachable` としてマークされます。

## Domainコマンド

### `spkt domain list`

全ドメインをNeuron数付きで表示します。

```bash
spkt domain list
spkt domain list --json
```

### `spkt domain rename`

ドメイン名を一括変更します。

```bash
spkt domain rename old-name new-name
```

### `spkt domain merge`

複数のドメインを1つに統合します。

```bash
spkt domain merge domain1 domain2 --into target-domain
```

### `spkt domain audit`

ドメインラベルとコミュニティ構造のズレを分析します。
ユーザーが付けたドメインと、グラフから自然に浮かび上がるコミュニティを
突き合わせて、以下のミスマッチを検出します:

- **分割**: ひとつのドメインが複数コミュニティにまたがっている → サブドメインを提案
- **統合**: 複数のドメインがひとつのコミュニティに集中している → マージを提案

コミュニティごとのTF-IDFキーワード抽出で命名のヒントも出します。

```bash
spkt domain audit
spkt domain audit --json
```

## Communityコマンド

### `spkt community detect`

Louvainアルゴリズムでコミュニティを検出します。

```bash
spkt community detect
spkt community detect -r 2.0              # 高解像度 = より多くのコミュニティ
spkt community detect --summarize          # コミュニティごとに要約Neuronも生成
spkt community detect --json
```

### `spkt community list`

現在のコミュニティ割り当てを表示します。

```bash
spkt community list
spkt community list --json
```

## 検索

### `spkt retrieve`

グラフ構造を考慮した検索。キーワード、セマンティック類似度、
FSRS検索可能性、中心性、復習圧力を総合的にスコアリングします。

```bash
spkt retrieve "圏論"
spkt retrieve "functor" --limit 5

# フィルタ付き検索
spkt retrieve "attention" --filter year=2017
spkt retrieve "GNN" --filter domain=cs --filter venue=NeurIPS
```

| オプション | 説明 |
|-----------|------|
| `--limit`, `-n` | 最大件数（デフォルト: 10） |
| `--filter KEY=VALUE` | Neuronフィールド（`type`, `domain`）またはSourceのfilterableメタデータでフィルタ。複数指定可。キーが存在しないSourceは除外。 |

## 復習

### `spkt quiz`

インタラクティブなフラッシュカード復習セッション。
理解度に応じた出題（Scaffold）で、セルフグレーディング形式です。

```bash
spkt quiz
spkt quiz --limit 10
```

## Brain健全性とインサイト

### `spkt stats`

Circuit統計を表示します: Neuron数、Synapse数、グラフ密度。

```bash
spkt stats
spkt stats --json
```

### `spkt diagnose`

Brainの健全性を診断します。孤立Neuron、弱いSynapse、
長期放置のNeuronなど、潜在的な問題を洗い出します。

```bash
spkt diagnose
spkt diagnose --json
```

### `spkt progress`

学習の進捗レポートを生成します。復習状況、定着率、
ドメインごとのカバレッジ、成長トレンドなどが確認できます。

```bash
spkt progress
spkt progress --format html -o progress.html
spkt progress --json
```

### `spkt manual`

Brainの中身からユーザーガイドを自動生成します。
ドメイン・トピック・復習期限・ソースを一覧化。

```bash
spkt manual
spkt manual --format html -o manual.html
spkt manual --write-meta                   # ガイドを_meta Neuronとしても書き込み
spkt manual --json
```

## 統合（Consolidation）

### `spkt consolidate`

睡眠中の記憶統合にヒントを得たグラフ最適化。Brainを分析し、
弱いSynapseの剪定や未使用接続の減衰を行う計画を生成します。

```bash
spkt consolidate                           # ドライラン — 計画を表示
spkt consolidate --domain math             # ドメインを限定
spkt consolidate --json
```

### `spkt consolidate apply`

統合計画を実行します。計画生成時のグラフ状態と現在の状態を
ハッシュで照合し、変更がないことを確認してから適用します。

```bash
spkt consolidate apply                     # ドライラン確認後に適用
spkt consolidate apply --json
```

## 可視化

### `spkt visualize`

インタラクティブなHTMLグラフを生成します。

```bash
spkt visualize
spkt visualize -o my-graph.html
```

## エクスポート / インポート

### `spkt export`

Brainをバックアップ・共有・デプロイ用にエクスポートします。

```bash
# tarball（フルバックアップ）
spkt export -o backup.tar.gz

# JSONバンドル（ポータブル、人間が読める）
spkt export --format json -o brain.json
spkt export --format json --include-embeddings -o brain-full.json

# QABotバンドル（デプロイ用の読み取り専用SQLite）
spkt export --format qabot -o qa-bundle.db
```

| フォーマット | 内容 | 用途 |
|------------|------|------|
| `tar`（デフォルト） | `.spikuit/`ディレクトリ全体 | バックアップ、移行 |
| `json` | Neuron、Synapse、SourceをJSON化 | 共有、検査 |
| `qabot` | エンベディング付きの最小SQLite | ポータブルRAGデプロイ |

**QABotバンドル**はNeuron・Synapse・エンベディング・出典だけを詰めた
軽量SQLiteです。FSRS状態や復習履歴は含みません。
`Circuit(read_only=True)` で読み込めます。

### `spkt import`

tarballバックアップをインポートします。

```bash
spkt import backup.tar.gz
```

## 非推奨コマンド

旧コマンドもまだ動きますが、stderrに非推奨の警告が出ます。
上のリソース指向形式への移行をお勧めします。

| 旧コマンド | 新コマンド |
|-----------|-----------|
| `spkt add` | `spkt neuron add` |
| `spkt list` | `spkt neuron list` |
| `spkt inspect` | `spkt neuron inspect` |
| `spkt fire` | `spkt neuron fire` |
| `spkt due` | `spkt neuron due` |
| `spkt link` | `spkt synapse add` |
| `spkt learn` | `spkt source ingest` |
| `spkt refresh` | `spkt source refresh` |
| `spkt communities` | `spkt community list` / `spkt community detect` |
