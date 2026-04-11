# CLIリファレンス

全コマンドが `--json` フラグに対応しています。

## グローバルオプション

ほとんどのコマンドで以下のフラグが使えます:

| オプション | 説明 |
|-----------|------|
| `--brain`, `-b` | Brainルートディレクトリ（自動探索を上書き） |
| `--json` | マシンリーダブルなJSON出力 |

## Brain管理

### `spkt init`

カレントディレクトリに新しいBrainを初期化します。
フラグなしでは対話ウィザードを起動します。
`--json` または `--provider` を明示すると非対話で実行されます。

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

現在のBrain設定を表示します。

```bash
spkt config
spkt config --json
```

### `spkt embed-all`

埋め込みのないNeuronをバックフィルします。
実行前にNeuron数と推定トークン数を表示し、確認を求めます。

```bash
spkt embed-all              # 対話式 — 実行計画を表示して確認
spkt embed-all --yes        # 確認をスキップ
```

## 知識管理

### `spkt add`

新しいニューロンをCircuitに追加します。

```bash
spkt add "# Functor\n\n圏の間の写像。" -t concept -d math
spkt add "内容" --type fact --domain physics
spkt add "内容" -t concept --source-url "https://example.com/paper.pdf" --source-title "論文"
```

| オプション | 説明 |
|-----------|------|
| `-t`, `--type` | ニューロンタイプ（例: `concept`, `fact`, `procedure`） |
| `-d`, `--domain` | 知識ドメイン（例: `math`, `french`） |
| `--source-url` | 出典URL（引用追跡用） |
| `--source-title` | 出典タイトル（`--source-url`と併用） |

### `spkt list`

Neuron一覧を表示します。メタデータやドメインの探索もできます。

```bash
spkt list
spkt list -t concept -d math
spkt list --limit 50

# メタデータ探索
spkt list --meta-keys --json          # 全Sourceのfilterable/searchableキー一覧
spkt list --meta-values year --json   # キーの値一覧（件数付き）
spkt list --domains --json            # ドメイン一覧（Neuron数付き）
```

| オプション | 説明 |
|-----------|------|
| `--meta-keys` | メタデータキー一覧（filterable + searchable） |
| `--meta-values KEY` | 指定キーの値一覧 |
| `--domains` | ドメイン一覧（Neuron数付き） |

### `spkt inspect`

ニューロンの詳細情報を表示します: コンテンツ、FSRS状態、圧力、出典、コミュニティ、接続シナプス。

```bash
spkt inspect <neuron-id>
spkt inspect <neuron-id> --json    # sources[]とcommunity_idを含む
```

### `spkt link`

2つのニューロン間にシナプスを作成します。

```bash
spkt link <pre-id> <post-id> --type requires
spkt link <a-id> <b-id> --type relates_to
```

| タイプ | 方向 | 用途 |
|--------|------|------|
| `requires` | 片方向 | Aを理解するにはBが必要 |
| `extends` | 片方向 | AはBを拡張する |
| `contrasts` | 双方向 | AとBは対比関係 |
| `relates_to` | 双方向 | 一般的な関連 |

## 復習

### `spkt fire`

復習イベントを記録します（スパイクを発火）。

```bash
spkt fire <neuron-id> --grade fire
spkt fire <neuron-id> -g strong
```

| グレード | 意味 | FSRS Rating |
|---------|------|-------------|
| `miss` | 失火（不正解） | Again |
| `weak` | 弱発火（怪しい） | Hard |
| `fire` | 発火（正解） | Good |
| `strong` | 強発火（完璧） | Easy |

### `spkt due`

復習期限のニューロンを表示します。

```bash
spkt due
spkt due -n 20
spkt due --json
```

### `spkt quiz`

インタラクティブなフラッシュカード復習セッションです。
Scaffold適応コンテンツでニューロンを提示し、セルフグレーディングを受け付けます。

```bash
spkt quiz
spkt quiz --limit 10
```

## ソース取り込み

### `spkt learn`

URL、ファイル、ディレクトリを取り込みます。Sourceレコードを作成し、
抽出したコンテンツをエージェント駆動のチャンキングに渡します。

```bash
# URL
spkt learn "https://example.com/article" -d cs --json

# ファイル
spkt learn ./notes.md -d math --json

# ディレクトリ（一括取り込み）
spkt learn ./papers/ -d cs --json
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

## コミュニティ

### `spkt communities`

Louvainアルゴリズムでナレッジグラフ内のコミュニティ（クラスタ）を表示・検出します。

```bash
spkt communities                   # 現在のコミュニティを表示
spkt communities --detect          # 再検出を実行
spkt communities --detect -r 2.0   # 高解像度 = より多くのコミュニティ
spkt communities --json            # マシンリーダブル出力
```

## 検索

### `spkt retrieve`

グラフ重み付き検索です。キーワードマッチング、意味的類似度、
FSRS検索可能性、グラフ中心性、復習圧力を組み合わせます。

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

## 可視化

### `spkt visualize`

インタラクティブなHTMLグラフ可視化を生成します。

```bash
spkt visualize
spkt visualize -o my-graph.html
```

## ソース管理

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

## ドメイン管理

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

## ソース鮮度管理

### `spkt refresh`

URLソースを再取得して変更を検出します。条件付きGET（ETag / Last-Modified）で
帯域を節約します。コンテンツが変わっていれば関連Neuronを再エンベディングします。

```bash
spkt refresh <source-id>          # 特定のSourceを更新
spkt refresh --stale 30           # 30日以上未取得のSourceを更新
spkt refresh --all                # 全URLソースを更新
```

404を返すSourceは `unreachable` としてマークされます。

## エクスポート / インポート

### `spkt export`

Brainをバックアップ、共有、デプロイ用にエクスポートします。

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

**QABotバンドル**はNeuron、Synapse、エンベディング、出典情報だけを含む
自己完結型SQLiteです。FSRS状態、復習履歴、生ソースファイルは含みません。
`Circuit(read_only=True)` で読み込みます。

### `spkt import`

tarballバックアップをインポートします。

```bash
spkt import backup.tar.gz
```

## 統計

### `spkt stats`

Circuit統計を表示します: Neuron数、Synapse数、グラフ密度。

```bash
spkt stats
spkt stats --json
```
