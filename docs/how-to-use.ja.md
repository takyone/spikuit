# 使い方

ユースケース別ガイド。コマンド一覧は[CLIリファレンス](cli.md)、
Python APIの詳細は[APIリファレンス](reference/index.md)を参照。

## CLIレシピ

### 知識の追加

```bash
# シンプルなコンセプト
spkt add "# Functor\n\n圏の間の構造を保つ写像。" -t concept -d math

# フロントマター付き
spkt add "---
type: concept
domain: french
---
# Subjonctif
疑い、感情、必要性を表すときに使用。"

# ファイルから
cat notes.md | spkt add -t note -d physics
```

### コンセプトの接続

```bash
# 「MonadはFunctorが前提」
spkt link <monad-id> <functor-id> -t requires

# 「HTTPとgRPCは対比」（双方向にエッジ作成）
spkt link <http-id> <grpc-id> -t contrasts
```

### 復習（フラッシュカード）

```bash
# 復習期限のものは？
spkt due

# インタラクティブなフラッシュカードセッション
spkt quiz

# 手動で記録（外部での復習後）
spkt fire <neuron-id> -g fire
```

### 検索と探索

```bash
# グラフ重み付き検索（キーワード + セマンティック + 記憶の強さ + 中心性）
spkt retrieve "functor"

# タイプ/ドメインで絞り込み
spkt list -t concept -d math

# Neuronの詳細（復習状態、隣接ノード）
spkt inspect <neuron-id>

# 統計
spkt stats
```

### 可視化

```bash
# インタラクティブなHTMLグラフを生成
spkt visualize -o graph.html
```

## エージェントスキル

スキルはLLM駆動のインタラクションモードで、
[Claude Code](https://docs.anthropic.com/en/docs/claude-code)
などの**Agent CLI**内で動作するよう設計されています。

コアエンジンはLLM非依存 — `spkt`コマンドは単独で動作します。
スキルはその上に会話的なインタラクション（チュータリング、
キュレーション、Q&A）を追加します。

```
┌──────────────────────────────────────────┐
│  Agent CLI (Claude Code, Codexなど)       │
│  ┌────────────────┐  ┌───────────────┐   │
│  │  LLM推論       │  │  シェルアクセス│   │
│  └───────┬────────┘  └───────┬───────┘   │
│          │   スキル / ツール  │            │
│          └────────┬──────────┘            │
│                   ▼                      │
│        spikuit-core Python API           │
│   (Circuit, Sessions, Learn)             │
│                   │                      │
│              spkt CLI                    │
└──────────────────────────────────────────┘
```

### `/tutor` — AIチューター

教え、クイズし、コーチする1対1のチューター — ただのクイズマシンではない。

チューターは状態を見て次のアクションを判断します：弱いコンセプトを教える、
理解度を確認するクイズ、間違いへのフィードバック、質問への回答。

**セッション例：**

```
> /tutor

Tutor: 5つのコンセプトが復習期限です。Functorの安定性が低く、
       Monadの前提知識になっているので、先に始めましょう。

       [講義] Functorは圏の間の構造を保つ写像です。
       「箱の中身に関数を適用できる」と考えてください...
       （既知のコンセプトを使って説明）

       理解度を確認します。

       [クイズ] Functorがマッピング時に保存すべきものは？

You:   圏の構造？

Tutor: [フィードバック] 方向は合っています。もう少し正確に言うと、
       Functorは恒等射と合成を保存する必要があります。
       つまり fmap id = id、fmap (f . g) = fmap f . fmap g です。

       別の角度から。

       [クイズ] Haskellで`fmap`と`map`が違うのはなぜ？

You:   mapはリスト専用で、fmapは任意のFunctorに使える？

Tutor: [フィードバック] その通り！`map`はリストに特化した関数で、
       `fmap`は任意のFunctorインスタンスに使える汎用版です。✅ fire
       安定性: 3.2 → 8.1日

       では、今学んだことをベースにMonadに進みましょう...
```

**チューターのアクション：**

| アクション | いつ | 例 |
|-----------|------|-----|
| 診断 | セッション開始 | 「Functorが弱く、Monadのブロッカー」 |
| 講義 | 新規/弱いコンセプト | 既知のコンセプトをアンカーにした構造化説明 |
| クイズ | 教えた後 | 多様な問題タイプ（「〜とは？」だけでない） |
| フィードバック | 回答後 | なぜ正解/不正解か、何が足りないか |
| Q&A | 質問時 | Brain知識を使った教育的な回答 |
| ドリル | 弱点の継続 | 角度を変えた集中反復 |

### `/learn` — ナレッジキュレーション

会話で知識を追加。エージェントが入力を構造化し、
関連コンセプトを発見し、接続を作成します。

**セッション例：**

```
> /learn

何を追加しますか？

> Haskellのモナドはbind (>>=)で計算を連鎖させる。
  IOとMaybeが代表例。

Neuronを作成します：

── Monad ──
# モナド (Monad)
bind (>>=) で計算を連鎖させる。
Examples: IO (副作用), Maybe (失敗処理)

関連コンセプトが2つ見つかりました：
  1. Functor (0.82) → requires
  2. Applicative (0.78) → requires

この接続で作成しますか？ [Y/n]

✅ n-abc123を追加、FunctorとApplicativeにリンク
```

### `/qabot` — ナレッジQ&A

Brainに質問して回答を得る。会話を通じて検索品質が向上。

**セッション例：**

```
> /qabot

何でも聞いてください。

> FunctorとApplicativeの違いは？

Functorは包まれた値に関数を適用できます（fmap）。
Applicativeはこれを拡張し、包まれた関数を包まれた値に適用できます（<*>）。
すべてのApplicativeはFunctorですが、Applicativeは独立した
エフェクトを合成する能力を追加します...

ソース: n-abc123 (Functor), n-def456 (Applicative), n-ghi789 (Monad)

> ApplicativeとMonadの関係をもう少し詳しく

[前の結果が自動的にペナルティ — 新しい資料を検索]

Over-smoothingはGCNの層を増やすとノード表現が収束する現象です...

ソース: n-jkl012, n-mno345

> ありがとう

✅ ソースをブースト — 将来の検索で優先されます
```

**フィードバックの仕組み：**

- **類似のフォローアップ** → 前の結果が不十分 → ペナルティ
- **感謝/承認** → 結果が役立った → ブースト
- **トピック変更** → セッションリセット
- **永続モード** → フィードバックがセッション間で維持

## Python API

カスタム統合、エージェント、LLMアダプター構築用。

### AutoQuiz（カスタムLLM）

```python
from spikuit_core import AutoQuiz, Circuit, QuizItem, QuizRequest, Grade

async def my_generate(req: QuizRequest) -> QuizItem:
    prompt = f"Neuron {req.primary}についての問題を生成"
    # ... LLMを呼び出す ...
    return QuizItem(question=q, answer=a, hints=[h1, h2])

async def my_grade(item: QuizItem, response: str) -> Grade:
    prompt = f"回答を採点: {response}\n期待: {item.answer}"
    # ... LLMを呼び出す ...
    return Grade.FIRE

quiz = AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade)
```

### TutorSession

```python
from spikuit_core import TutorSession, AutoQuiz, Flashcard

# Flashcard（LLM不要）
tutor = TutorSession(circuit, learn=Flashcard(circuit))

# AutoQuiz（LLM駆動）
tutor = TutorSession(
    circuit,
    learn=AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade),
)

queue = await tutor.start(limit=5)
state = await tutor.teach()
state = await tutor.respond("回答")
```

### QABotSession

```python
from spikuit_core import QABotSession

session = QABotSession(circuit, persist=True)

# 質問 — スコア付き、重複排除済みの結果
results = await session.ask("Functorとは？")

# ポジティブフィードバック — 有用なNeuronをブースト
await session.accept([results[0].neuron_id])

# フォローアップ — 類似なら前の結果を自動ペナルティ
results = await session.ask("Haskellでのfunctorの例は？")

await session.close()  # ブーストをDBにコミット
```

### LearnSession

```python
from spikuit_core import LearnSession, SynapseType

session = LearnSession(circuit)

# 知識を追加 — 関連コンセプトを自動発見
neuron, related = await session.ingest(
    "# Functor\n\n圏の間の構造を保つ写像。",
    type="concept", domain="math",
)

# 接続を作成
if related:
    await session.relate(neuron.id, related[0].id, SynapseType.REQUIRES)

# 重複をマージ
await session.merge(["n-old1", "n-old2"], into_id="n-keep")

await session.close()
```
