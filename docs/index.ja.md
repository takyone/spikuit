# Spikuit

**使うほど賢くなるナレッジベース**

---

Spikuit（spike + circuit、発音: /spaɪ.kɪt/）は、**検索、復習、質問のすべてがシステムを改善する**パーソナルナレッジシステムです。

## 何ができる？

### 一緒に育つナレッジグラフ

```bash
spkt add "# Functor\n\n圏の間の構造を保つ写像。" -t concept -d math
spkt add "# Monad\n\n自己関手の圏におけるモノイド。" -t concept -d math
spkt link <monad-id> <functor-id> -t requires
```

コンセプトが互いにつながる。検索結果は関連度、理解度、
グラフ内の中心性によってランク付けされます。

### AIチューターと学ぶ

```
> /tutor

Tutor: 「Functor」の理解度が低く、「Monad」の前提知識になっています。
       まずFunctorから説明して、理解度を確認しましょう。
       ...
       [教える → クイズ → フィードバック → 弱い部分を再説明]
```

ただのフラッシュカードではなく、弱点を診断し、概念を教え、
理解をテストし、間違いをコーチングするチューター。

### AIエージェントにナレッジを与える

```python
session = QABotSession(circuit, persist=True)
results = await session.ask("Functorとは？")
await session.accept([results[0].neuron_id])
# → 役立った結果が将来の検索でブーストされる
```

検索品質は会話のフィードバックで改善 — 再インデックスは不要。

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
# エンベディング設定、Agent CLIスキル（/tutor, /learn, /qabot）のインストールも行えます
spkt init

# ナレッジを追加
spkt add "# Functor\n\n圏の間の構造を保つ写像。" -t concept -d math

# 復習対象を確認
spkt due
spkt quiz

# 検索
spkt retrieve "functor"

# ナレッジグラフを可視化
spkt visualize
```

### Agent CLIスキル

`spkt init` でAgent CLI（Claude Code、Cursor、Codex）向けのスキルをインストールできます。
個別にインストールすることも可能です：

```bash
spkt skills install                    # デフォルト: .claude/skills/
spkt skills install -t .cursor/skills  # Cursor用
```

インストール後、Agent CLIから `/tutor`、`/learn`、`/qabot` が使えます。

## ドキュメント

- [はじめに](getting-started.ja.md) — インストール、初期化、最初のコマンド
- [使い方](how-to-use.ja.md) — ユースケース、エージェントスキル、Python API
- [コンセプト](concepts.ja.md) — Brain、グラフモデル、つながりの仕組み
- [CLIリファレンス](cli.ja.md) — 全`spkt`コマンド
- [付録](appendix.ja.md) — アルゴリズムと技術的詳細
- [APIリファレンス](reference/index.md) — Python APIドキュメント

## ライセンス

Apache-2.0
