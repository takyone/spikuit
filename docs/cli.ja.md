# CLIリファレンス

全コマンド `--json` フラグ対応。

## グローバルオプション

ほとんどのコマンドで以下のフラグが使える:

| オプション | 説明 |
|-----------|------|
| `--brain`, `-b` | Brainルートディレクトリ（自動探索を上書き） |
| `--json` | マシンリーダブルなJSON出力 |

## Brain管理

### `spkt init`

カレントディレクトリに新しいBrainを初期化する。
フラグなしでは対話ウィザードを起動。
`--json` または `--provider` を明示すると非対話で実行。

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

現在のBrain設定を表示する。

```bash
spkt config
spkt config --json
```

### `spkt embed-all`

既存のニューロンで埋め込みがないものをバックフィルする。

```bash
spkt embed-all
```

## 知識管理

### `spkt add`

新しいニューロンをCircuitに追加する。

```bash
spkt add "# Functor\n\n圏の間の写像。" -t concept -d math
spkt add "内容" --type fact --domain physics --source "教科書 p.42"
```

| オプション | 説明 |
|-----------|------|
| `-t`, `--type` | ニューロンタイプ（例: `concept`, `fact`, `procedure`） |
| `-d`, `--domain` | 知識ドメイン（例: `math`, `french`） |
| `-s`, `--source` | 出典URLまたは参照 |

### `spkt list`

ニューロン一覧（フィルタ付き）。

```bash
spkt list
spkt list -t concept -d math
spkt list --limit 50
```

### `spkt inspect`

ニューロンの詳細情報: コンテンツ、FSRS状態、圧力、接続シナプス。

```bash
spkt inspect <neuron-id>
spkt inspect <neuron-id> --json
```

### `spkt link`

2つのニューロン間にシナプスを作成する。

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

復習イベントを記録する（スパイクを発火）。

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

復習期限のニューロンを表示する。

```bash
spkt due
spkt due -n 20
spkt due --json
```

### `spkt quiz`

インタラクティブなフラッシュカード復習セッション。
Scaffold適応コンテンツでニューロンを提示し、セルフグレーディングを受け付ける。

```bash
spkt quiz
spkt quiz --limit 10
```

## 検索

### `spkt retrieve`

グラフ重み付き検索。キーワードマッチング、意味的類似度、
FSRS検索可能性、グラフ中心性、復習圧力を組み合わせる。

```bash
spkt retrieve "圏論"
spkt retrieve "functor" --limit 5
```

## 可視化

### `spkt visualize`

インタラクティブなHTMLグラフ可視化を生成する。

```bash
spkt visualize
spkt visualize -o my-graph.html
```

## 統計

### `spkt stats`

Circuit統計: ニューロン数、シナプス数、グラフ密度。

```bash
spkt stats
spkt stats --json
```
