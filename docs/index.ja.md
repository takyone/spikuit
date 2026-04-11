# Spikuit

**使うほど賢くなるナレッジベース**

---

Spikuit（spike + circuit、発音: /spaɪ.kɪt/）は、**検索、復習、質問のすべてがシステムを改善する**パーソナルナレッジシステムです。

## 何ができますか？

### /learn → /qabot : 自己成長するRAG

記事、メモ、URLをBrainに取り込んで、自然言語で質問できます。
回答にはソースの引用が含まれます。検索品質は会話ごとに改善されます —
役に立たない結果は自動的にペナルティされ、役立つ結果はブーストされます。

```
You: /learn
     この論文をBrainにまとめて: https://arxiv.org/abs/1706.03762

Agent: 8 neurons追加（Multi-Head Attention, Scaled Dot-Product, ...）。
       6 synapses作成、引用用にSource紐付け。

You: /qabot
     Multi-Head Attentionとシングルヘッドの違いは？

Agent: Multi-Head Attentionは複数のAttention関数を並列実行し...
       ソース:
       - [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
```

### /learn → /tutor : AI学習パートナー

学習素材からナレッジグラフを構築し、AIチューターに
教えてもらえます。前提知識を検出し、難易度を調整し、
間違いにはフィードバックが付きます — 「正解」「不正解」だけではありません。

```
You: /learn
     圏論を勉強中。キーコンセプト:
     - Functor: 圏の間の構造を保つ写像
     - 自然変換: Functor間の射
     - Monad: 自己関手の圏におけるモノイド

Agent: 3 neurons追加、2 synapses作成（Monad/自然変換 --requires--> Functor）。

You: /tutor

Tutor: まずFunctorから始めましょう — 他の2つの前提知識です。
       [教える → クイズ → フィードバック → 弱い部分を再説明]
```

## 仕組み

1. **スマートなスケジューリング** — 各コンセプトに理解度に基づく復習タイミングがあります
   （[FSRS](https://github.com/open-spaced-repetition/fsrs4anki)）
2. **活性化の伝播** — 一つのコンセプトを復習すると、関連コンセプトの
   復習タイミングが近づきます。一緒に使う接続は強くなります。
3. **検索の最適化** — 関連度 × 記憶の強さ × グラフ中心性でランク付けします。
   フィードバックで継続的に改善されます。

## クイックスタート

```bash
# インストール
pip install spikuit

# Brainの初期化（対話式ウィザード）
# エンベディング設定やAgent CLIスキル（/tutor, /learn, /qabot）のインストールも行えます
spkt init
```

Agent CLI（Claude Code、Cursor、Codex）から：

```
/learn    → 会話、メモ、URLからナレッジを追加
/qabot    → 質問して引用付きの回答を得る
/tutor    → レベルに合わせたAIチューターと学ぶ
```

`spkt` コマンドを直接使うこともできます:

```bash
spkt learn "https://example.com/article" -d cs --json
spkt retrieve "query"
spkt communities --detect
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
