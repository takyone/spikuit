# Spikuit

[English](../README.md) | [日本語](README.ja.md)

**シナプスに着想を得た間隔反復エンジン**

FSRS × ナレッジグラフ × 活性化拡散

---

## Spikuit とは？

Spikuit（spike + circuit、発音: /spaɪ.kɪt/）は、記憶を神経回路としてモデル化する間隔反復システムです。ある概念を復習すると、つながった知識へ活性化が伝播し、使う経路は強化され、使わない経路は自然に減衰します。

**勉強するだけ。ナレッジグラフは勝手にできる。**

ノート整理不要。リンク管理不要。フォルダ分け不要。
復習するだけで、あなたの知識に合わせてグラフが成長・適応します。

### ビジョン

Spikuit は既存の優れたツールからアイデアを得て、それらを一つにまとめることを目指しています:

| インスピレーション元 | リスペクトする点 | Spikuit が探求すること |
|---------------------|-----------------|----------------------|
| Anki | 最高水準のスケジューリング | スケジューリングの上に概念間の関係を乗せる |
| Obsidian | 豊かな知識リンク | リンクと間隔反復を組み合わせる |
| DeepTutor | 文脈を考慮した学習支援 | 長期記憶の定着をループに統合する |

目指すのは **学習 → 定着 → 検索** が一つの流れとして機能するシステムです。これらのツールを置き換えるのではなく、補完する存在を目指します。

## ニューロンモデル

Spikuit は神経科学に直接対応します:

| 脳 | Spikuit | 役割 |
|----|---------|------|
| ニューロン | `Neuron` | 知識の単位（Markdown） |
| シナプス | `Synapse` | 型付き・重み付きの接続 |
| スパイク | `Spike` | 復習イベント（活動電位） |
| 回路 | `Circuit` | ナレッジグラフ全体 |
| 可塑性 | `Plasticity` | チューニング可能な学習パラメータ |

## アルゴリズム

| アルゴリズム | 着想元 | 機能 |
|-------------|--------|------|
| **FSRS** | エビデンスベースのスケジューリング | ノード単位の間隔反復 |
| **APPNP** | Personalized PageRank | 1ノード復習 → 近傍ノードを活性化 |
| **STDP** | スパイクタイミング依存可塑性 | 一緒に復習した概念間の接続を強化 |
| **LIF** | 漏れ積分発火モデル | 復習圧力の蓄積と減衰 |
| **グラフ重み付き検索** | Brain PageRank | 関連度 × 記憶強度 × 中心性でランキング |

## クイックスタート

```bash
# インストール
git clone https://github.com/takyone/spikuit.git
cd spikuit
uv sync --package spikuit-cli

# 知識を追加
spkt add "# Functor\n\n圏の間の写像。" -t concept -d math
spkt add "# Monad\n\n自己関手の圏におけるモノイド。" -t concept -d math

# 接続
spkt link <neuron-a> <neuron-b> --type requires

# 復習
spkt fire <neuron-id> --grade fire

# 復習期限の確認
spkt due

# 検索（FSRS検索可能性 + グラフ中心性 + 圧力でランキング）
spkt retrieve "functor"

# 可視化
spkt visualize
```

## CLI コマンド

| コマンド | 説明 |
|---------|------|
| `spkt add` | Neuron を追加 |
| `spkt fire` | Spike を発火（復習 + 伝播 + STDP） |
| `spkt due` | 復習期限の Neuron を表示 |
| `spkt retrieve` | グラフ重み付き検索 |
| `spkt list` | Neuron 一覧（type/domain フィルタ） |
| `spkt link` | Synapse を作成 |
| `spkt inspect` | Neuron 詳細: FSRS状態、圧力、隣接ノード |
| `spkt stats` | 回路の統計情報 |
| `spkt visualize` | インタラクティブなグラフ可視化（HTML） |

## アーキテクチャ

```
spikuit/
├── spikuit-core/      # LLM非依存エンジン
│   ├── models.py      #   Neuron, Synapse, Spike, Plasticity (msgspec)
│   ├── circuit.py     #   公開API: fire, retrieve, ensemble, due
│   ├── propagation.py #   APPNP拡散 + STDP + LIF減衰
│   └── db.py          #   非同期SQLite永続化
├── spikuit-cli/       # spkt コマンド (Typer)
└── spikuit-agents/    # クイズ生成レイヤー（予定）
```

### `fire()` の処理フロー

```
circuit.fire(spike)
  1. スパイクをDBに記録
  2. FSRS: stability, difficulty を更新、次回復習をスケジュール
  3. APPNP: 近傍ノードへ活性化を伝播（圧力デルタ）
  4. 発火元ニューロンの圧力をリセット
  5. STDP: 共発火タイミングに基づきエッジ重みを更新
  6. 次回STDP用に最終発火タイムスタンプを記録
```

### 技術スタック

- **モデル**: msgspec.Struct（型安全、高速シリアライゼーション）
- **ストレージ**: SQLite (aiosqlite) + NetworkX（インメモリグラフ）
- **スケジューリング**: FSRS v6
- **CLI**: Typer
- **可視化**: pyvis (vis.js)
- **言語**: Python 3.11+

## 開発

```bash
# セットアップ
uv sync --package spikuit-core --extra dev

# テスト実行（56テスト）
uv run --package spikuit-core pytest spikuit-core/tests/ -v

# CLI開発
uv run --package spikuit-cli spkt --help
```

## ライセンス

Apache-2.0
