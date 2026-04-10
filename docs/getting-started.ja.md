# はじめに

## インストール

```bash
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-cli
```

## Brainの初期化

Brainはプロジェクトローカルな `.spikuit/` ディレクトリ（`.git/` のようなもの）で、
設定・データベース・キャッシュを含みます。

```bash
# 基本の初期化（埋め込みなし）
spkt init

# ローカル埋め込み付き（LM Studio）
spkt init -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5

# Ollama
spkt init -p ollama \
  --base-url http://localhost:11434 \
  --model nomic-embed-text

# 設定確認
spkt config
```

作成されるもの:

```
.spikuit/
├── config.toml    # Brain設定
├── circuit.db     # SQLiteデータベース
└── cache/         # 埋め込みキャッシュ
```

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

| グレード | 意味 | FSRS Rating |
|---------|------|-------------|
| `miss` | 失火（不正解） | Again |
| `weak` | 弱発火（怪しい） | Hard |
| `fire` | 発火（正解） | Good |
| `strong` | 強発火（完璧） | Easy |

## シナプスタイプ

| タイプ | 方向 | 用途 |
|--------|------|------|
| `requires` | 片方向 | Aを理解するにはBが必要 |
| `extends` | 片方向 | AはBを拡張する |
| `contrasts` | 双方向 | AとBは対比関係 |
| `relates_to` | 双方向 | 一般的な関連 |
