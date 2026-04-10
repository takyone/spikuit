# はじめに

## インストール

```bash
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-cli
```

## Brainの初期化

**Brain**は自己完結型のナレッジ空間 — Obsidian vaultやgitリポジトリのようなもの。
各Brainは独自のナレッジグラフ、設定、復習スケジュールを持つ。
ドメインやプロジェクトごとに複数のBrainを持てる。

`spkt init` で対話ウィザードを起動:

```
$ spkt init

Brain name [my-project]: math
Configure embeddings? [y/N]: y
  Providers: openai-compat, ollama
  Provider [openai-compat]:
  Base URL [http://localhost:1234/v1]:
  Model [text-embedding-nomic-embed-text-v1.5]:
  Dimension [768]:

--- Summary ---
Brain:    math
Location: /home/user/math/.spikuit/
Embedder: openai-compat
  URL:    http://localhost:1234/v1
  Model:  text-embedding-nomic-embed-text-v1.5
  Dim:    768

Create brain? [Y/n]:

Initialized brain 'math' at /home/user/math/.spikuit/
```

フラグを使えば非対話で初期化もできる:

```bash
spkt init -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5
```

作成されるもの:

```
.spikuit/
├── config.toml    # Brain設定
├── circuit.db     # SQLiteデータベース
└── cache/         # 埋め込みキャッシュ
```

gitと同様に、`spkt`はカレントディレクトリから上に辿って`.spikuit/`を自動探索する。
別のBrainを操作するには `--brain <パス>` を使う。

## 知識を追加する

```bash
# コンセプトを追加
spkt add "# Functor\n\n圏の間の写像で、構造を保存する。" \
  -t concept -d math

# もう一つ追加
spkt add "# Monad\n\n自己関手の圏におけるモノイド。" \
  -t concept -d math
```

## 概念を接続する

```bash
# MonadにはFunctorの理解が必要
spkt link <monad-id> <functor-id> --type requires

# 接続を確認
spkt inspect <monad-id>
```

## 復習する

```bash
# 復習期限のニューロンは？
spkt due

# 復習する（グレード: miss/weak/fire/strong）
spkt fire <neuron-id> --grade fire

# インタラクティブクイズ
spkt quiz
```

## 検索する

```bash
# グラフ重み付き検索
spkt retrieve "圏論"

# 意味検索のために埋め込みをバックフィル
spkt embed-all
```

## 可視化

```bash
# インタラクティブなHTMLグラフを生成
spkt visualize
```

## グレード一覧

| グレード | 意味 |
|---------|------|
| `miss` | 思い出せなかった |
| `weak` | 不確か |
| `fire` | 正解 |
| `strong` | 完璧 |

## シナプスタイプ

| タイプ | 方向 | 用途 |
|--------|------|------|
| `requires` | 片方向 | Aを理解するにはBが必要 |
| `extends` | 片方向 | AはBを拡張する |
| `contrasts` | 双方向 | AとBは対比関係 |
| `relates_to` | 双方向 | 一般的な関連 |
