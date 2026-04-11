# Spikuit

**会話で育てるナレッジグラフ**

---

Spikuit（spike + circuit、発音: /spaɪ.kɪt/）は、ナレッジ管理の最も難しい部分
— 取り込み、構造化、メンテナンス — をAIエージェントとの対話で自動化する
パーソナルナレッジシステムです。

従来のRAGシステムはデータ整備で破綻します。チャンキング、タグ付け、
関連付け、鮮度管理。Spikuitはこれを **Conversational Curation**
（対話型キュレーション）で解決します — 会話するだけでナレッジベースが育ちます。

## 3つのスキル、1つのループ

### `/spkt-learn` — 話して取り込む

記事、メモ、URLをBrainに取り込みます。エージェントがコンテンツを分割し、
関連を発見し、ナレッジグラフを構築します — あなたは話すだけ。

```
You: /spkt-learn
     この論文をBrainにまとめて: https://arxiv.org/abs/1706.03762

Agent: 8 neurons追加（Multi-Head Attention, Scaled Dot-Product, ...）。
       6 synapses作成、引用用にSource紐付け。
```

### `/spkt-qabot` — 聞いて引き出す

Brainに自然言語で質問できます。回答にはソースの引用が含まれます。
検索品質は会話ごとに改善されます — 役に立たない結果は自動的にペナルティされ、
役立つ結果はブーストされます。

```
You: /spkt-qabot
     Multi-Head Attentionとシングルヘッドの違いは？

Agent: Multi-Head Attentionは複数のAttention関数を並列実行し...
       ソース:
       - [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
```

### `/spkt-tutor` — 任せて学ぶ

ナレッジグラフの上に構築されたAIチューター。前提知識を検出し、
難易度を調整し、間違いにはフィードバックが付きます
— 「正解」「不正解」だけではありません。

```
You: /spkt-tutor

Tutor: まずFunctorから始めましょう — 他の2つの前提知識です。
       [教える → クイズ → フィードバック → 弱い部分を再説明]
```

## 仕組み

1. **スマートなスケジューリング** — 各コンセプトに理解度に基づく復習タイミング
   （[FSRS](https://github.com/open-spaced-repetition/fsrs4anki)）
2. **活性化の伝播** — 一つのコンセプトを復習すると、関連コンセプトの
   復習タイミングが近づく。一緒に使う接続は強くなる。
3. **検索の最適化** — 関連度 × 記憶の強さ × グラフ中心性でランク付け。
   フィードバックで継続的に改善。

## クイックスタート

```bash
# インストール
pip install spikuit

# Brainの初期化（対話式ウィザード）
spkt init
```

Agent CLI（Claude Code、Cursor、Codex）から：

```
/spkt-learn    → 話して取り込む。会話でナレッジをキュレーション。
/spkt-qabot    → 聞いて引き出す。引用付きの回答をナレッジグラフから。
/spkt-tutor    → 任せて学ぶ。レベルに合わせたAIチューターと。
```

`spkt` コマンドを直接使うこともできます:

```bash
spkt learn ./papers/ -d cs --json     # ディレクトリ一括取り込み
spkt retrieve "query" --filter domain=math
spkt export -o brain.json --format json
spkt visualize
```

## ドキュメント

- [はじめに](getting-started.ja.md) — インストール、初期化、最初のコマンド
- [使い方](how-to-use.ja.md) — ユースケース、エージェントスキル、Python API
- [コンセプト](concepts.ja.md) — Brain、グラフモデル、つながりの仕組み
- [CLIリファレンス](cli.ja.md) — 全`spkt`コマンド
- [付録](appendix.ja.md) — アルゴリズムと技術的詳細
- [APIリファレンス](reference/index.md) — Python APIドキュメント

## ライセンス

Apache-2.0
