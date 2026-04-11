# 認知・発達心理学

### 忘却曲線と間隔反復

<div class="chart-container">
  <canvas data-chart="forgetting-curve"></canvas>
</div>

- 記憶は時間とともに指数的に薄れる（Ebbinghaus, 1885）
- うまく思い出すたびに記憶の痕跡が強化され、次に忘れるまでの間隔が延びる
- 最適なタイミング: 忘れかけた頃に復習する
- Spikuitでは: FSRS v6がNeuronごとの安定性と難易度をモデル化

### テスティング効果

- 自分で思い出すほうが、読み返すより定着する（Roediger & Karpicke, 2006）
- 思い出せなかった場合でも、思い出そうとした試み自体が後の記憶を助ける
- Spikuitでは: 「見せて終わり」ではなく「出題→評価」の形式を採用

### ZPDとスキャフォールディング

<div class="zpd-diagram">
  <div class="zpd-outer">
    <span class="zpd-label">まだできない</span>
    <div class="zpd-mid">
      <span class="zpd-label">ZPD: 支援があればできる</span>
      <div class="zpd-inner">
        <span class="zpd-label">一人でできる</span>
        <span class="zpd-sublabel">（習得済み）</span>
      </div>
    </div>
  </div>
</div>

- ZPD（Vygotsky, 1978）: 一人でできることと、助けがあればできることの間の領域
- スキャフォールディング（Wood, Bruner & Ross, 1976）: できるようになるにつれて少しずつ外していく一時的な支え
- Spikuitでは: FSRS状態 + グラフ近傍からScaffoldレベルを算出

### スキーマ理論

- スキーマ = 知識を整理するための心の枠組み（Bartlett, 1932; Piaget）
- 新しい情報は既存のスキーマにつなげると覚えやすい
- Spikuitでは: ナレッジグラフ*そのもの*がスキーマ。`LearnSession.ingest()`が関連概念を自動で見つけ出す

### 参考文献

- Ebbinghaus, H. (1885). *Über das Gedächtnis*. Duncker & Humblot.（英訳: *Memory: A Contribution to Experimental Psychology*, 1913.）
- Bartlett, F. C. (1932). *Remembering: A Study in Experimental and Social Psychology*. Cambridge University Press.
- Vygotsky, L. S. (1978). *Mind in Society: The Development of Higher Psychological Processes*. Harvard University Press.
- Wood, D., Bruner, J. S. & Ross, G. (1976). The role of tutoring in problem solving. *Journal of Child Psychology and Psychiatry*, 17(2), 89–100.
- Roediger, H. L. & Karpicke, J. D. (2006). Test-enhanced learning: taking memory tests improves long-term retention. *Psychological Science*, 17(3), 249–255.
- Piaget, J. (1952). *The Origins of Intelligence in Children*. International Universities Press.
