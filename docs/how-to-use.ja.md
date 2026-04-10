# 使い方

ユースケース別ガイド。コマンド一覧は[CLIリファレンス](cli.md)、
Python APIの詳細は[APIリファレンス](reference/index.md)を参照。

## CLIレシピ

### 知識を追加する

```bash
# シンプルなコンセプト
spkt add "# 関手\n\n圏の間の写像。" -t concept -d math

# フロントマター付き
spkt add "---
type: concept
domain: french
---
# 接続法
疑い・感情・必要性を表すときに使う。"

# ファイルから
cat notes.md | spkt add -t note -d physics
```

### 概念を接続する

```bash
# 「モナドは関手を前提とする」
spkt link <monad-id> <functor-id> -t requires

# 「HTTPはgRPCと対比関係」（双方向にエッジ作成）
spkt link <http-id> <grpc-id> -t contrasts
```

### 復習する（フラッシュカード）

```bash
# 期限切れのニューロン一覧
spkt due

# インタラクティブなフラッシュカード
spkt quiz

# 外部復習後の手動fire
spkt fire <neuron-id> -g fire
```

### 検索・探索する

```bash
# グラフ重み付き検索（キーワード + 意味 + FSRS + 中心性）
spkt retrieve "関手"

# type/domainでフィルタ
spkt list -t concept -d math

# ニューロンの詳細（FSRS状態、圧力、近傍）
spkt inspect <neuron-id>

# 統計
spkt stats
```

### 可視化する

```bash
# インタラクティブなHTMLグラフを生成
spkt visualize -o graph.html
```

## 会話型セッション（Skills）

セッションはLLM駆動のインタラクションモード。
Claude CodeのSkillとして実行するのが最適。

### `/tutor` — スキャフォールド型チュータリング

1対1のチュータリング。ヒント段階開示、ギャップ検出、リトライ機能。

**動作:**

1. 復習期限のニューロンを選択（または明示的にIDを指定）
2. 弱い前提条件（ギャップ）を検出し、先にキューに挿入
3. Scaffoldレベルに応じた難易度で出題
4. 不正解時: 段階的ヒント開示 → リトライ
5. 最大試行回数到達: 答えを開示
6. `circuit.fire()` でグレードを記録 → FSRSスケジューリング更新

**フロー例:**

```
> /tutor

チュータリングセッション開始... 5ニューロンをキュー。
ギャップ検出: 「関手」は「モナド」の弱い前提条件 → 先に復習します。

── 関手 ──
Q: 関手とは何ですか？

> 写像？

近いですが不完全です。ヒント:
💡 何と何の*間*の写像か考えてみてください。

> 圏と圏の間の構造を保つ写像

✅ 正解！（Grade: FIRE）

── モナド ──
Q: モナドは関手とどう関係しますか？
...
```

### `/learn` — ナレッジキュレーション

対話を通じてニューロン追加、関連発見、重複統合。

**動作:**

1. コンテンツ（テキスト、メモ、アイデア）を提供
2. `ingest()` でニューロン作成 + 関連概念を自動発見
3. `relate()` でシナプス作成・強化
4. `merge()` で重複ニューロンを統合（シナプス転送 + コンテンツ結合）
5. `search()` でグラフ内の関連知識を検索

**フロー例:**

```
> /learn

何を追加しますか？

> Yコンビネータはラムダ計算において、
  名前付き関数なしで再帰を可能にする。

ニューロン「Yコンビネータ」(n-a3f2b1) を追加しました。
関連する概念が3つ見つかりました:
  - 「ラムダ計算」（類似度 0.82）
  - 「不動点」（類似度 0.71）
  - 「再帰」（類似度 0.68）

リンクしますか？（yes/no/選択）

> 全部リンクして

シナプスを3つ作成しました（relates_to）。

> あ、Yコンビネータはラムダ計算をrequiresだな

更新: Yコンビネータ → ラムダ計算 (requires)
```

### `/review` — 間隔反復レビュー

AutoQuizを使った復習セッション。保存済み or LLM生成の問題を出題。

**動作:**

1. 復習期限のニューロンを取得
2. 各ニューロンについて:
    - 保存済みQuizItemがあればそれを出題（プレビューモード）
    - なければLLMで新問題を生成（生成モード）
    - LLM未設定ならフラッシュカードフォールバック
3. 回答を評価（LLM採点 or セルフグレード）
4. グレード記録 → FSRS更新 → 近傍への伝播

**フロー例:**

```
> /review

5ニューロンが復習期限です。

── 1/5: 接続法 ──
Q: フランス語で接続法を使う場面は？
   トリガーカテゴリを2つ、例文付きで挙げてください。

> "je doute que" のような疑いの表現の後と、
  "je suis content que" のような感情の表現の後

✅ Grade: FIRE
   Stability: 8.2 → 14.1日

── 2/5: 関手 ──
Q: 関手が保存しなければならないものは何ですか？

> ...
```

## Python API

カスタム連携、エージェント、LLMアダプター構築用。

### AutoQuiz + カスタムLLM

```python
from spikuit_core import AutoQuiz, Circuit, QuizItem, QuizRequest, Grade

# あなたのLLM連携
async def my_generate(req: QuizRequest) -> QuizItem:
    prompt = f"ニューロン {req.primary} について問題を生成"
    # ... LLM呼び出し ...
    return QuizItem(question=q, answer=a, hints=[h1, h2])

async def my_grade(item: QuizItem, response: str) -> Grade:
    prompt = f"この回答を採点: {response}\n期待: {item.answer}"
    # ... LLM呼び出し ...
    return Grade.FIRE  # or MISS/WEAK/STRONG

# 使い方
quiz = AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade)
neuron_ids = await quiz.select(limit=5)
for nid in neuron_ids:
    scaffold = quiz.scaffold(nid)
    item = await quiz.present(nid, scaffold)
    # ... ユーザーに表示、回答を取得 ...
    grade = await quiz.evaluate(nid, item, response)
    await quiz.record(nid, grade)
```

### TutorSession の構成

```python
from spikuit_core import TutorSession, AutoQuiz, Flashcard, Circuit

# Flashcard使用（LLM不要）
tutor = TutorSession(circuit, learn=Flashcard(circuit))

# AutoQuiz使用（LLM駆動）
tutor = TutorSession(
    circuit,
    learn=AutoQuiz(circuit, generate_fn=my_generate, grade_fn=my_grade),
    max_attempts=3,
)

queue = await tutor.start(limit=5)
while True:
    state = await tutor.teach()
    if state is None:
        break
    print(state.item.question)
    answer = input("> ")
    state = await tutor.respond(answer)
    if state.grade in (Grade.MISS, Grade.WEAK) and tutor.current:
        hint = tutor.hint()
        if hint:
            print(f"ヒント: {hint}")
            answer = input("> ")
            state = await tutor.respond(answer)

print(tutor.stats)
```

### QuizItem の永続化

```python
from spikuit_core import QuizItem, QuizItemRole, ScaffoldLevel

# QuizItem を保存（ニューロンとM:N関連）
item = QuizItem(
    question="関手とは何ですか？",
    answer="構造を保存する圏の間の写像。",
    hints=["射について考えてみて。", "対象と射の両方を写す。"],
    grading_criteria="圏と構造保存に言及すること。",
    scaffold_level=ScaffoldLevel.MINIMAL,
    neuron_ids={
        "n-abc123": QuizItemRole.PRIMARY,
        "n-def456": QuizItemRole.SUPPORTING,
    },
)
await circuit.add_quiz_item(item)

# ニューロンのQuizItemを取得
items = await circuit.get_quiz_items("n-abc123", role=QuizItemRole.PRIMARY)
items = await circuit.get_quiz_items("n-abc123", scaffold_level=ScaffoldLevel.NONE)

# 削除
await circuit.remove_quiz_item(item.id)
```
